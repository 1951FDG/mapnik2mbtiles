# pylint: disable=W0707

import json
import logging
import math
import os
import shutil
import sys
import threading
from argparse import ArgumentParser
from queue import Queue

import mapnik
from mbutil import disk_to_mbtiles

DEG_TO_RAD = math.pi / 180
RAD_TO_DEG = 180 / math.pi

MERC_MAX_LATITUDE = 85.0511287798065923778

MAPNIK_LONGLAT_PROJ = "+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs"


class GoogleProjection:
    def __init__(self, levels, tile_size):
        self.Bc = []
        self.Cc = []
        self.zc = []
        self.Ac = []
        c = tile_size

        for _ in range(0, levels):
            e = c / 2
            self.Bc.append(c / 360.0)
            self.Cc.append(c / (2 * math.pi))
            self.zc.append((e, e))
            self.Ac.append(c)
            c *= 2

    def from_ll_to_pixel(self, ll, zoom):
        d = self.zc[zoom]
        e = round(d[0] + ll[0] * self.Bc[zoom])
        f = min(max(math.sin(DEG_TO_RAD * ll[1]), -0.9999), 0.9999)
        g = round(d[1] + 0.5 * math.log((1 + f) / (1 - f)) * -self.Cc[zoom])
        return e, g

    def from_pixel_to_ll(self, px, zoom):
        e = self.zc[zoom]
        f = (px[0] - e[0]) / self.Bc[zoom]
        g = (px[1] - e[1]) / -self.Cc[zoom]
        h = RAD_TO_DEG * (2 * math.atan(math.exp(g)) - 0.5 * math.pi)
        return f, h


class RenderThread:
    def __init__(self, q, map_file, map_prj, max_zoom, tile_size, tile_fmt):
        self.q = q
        self.m = mapnik.Map(tile_size, tile_size)
        self.m.aspect_fix_mode = mapnik.aspect_fix_mode.RESPECT

        # Load style XML
        mapnik.load_map(self.m, map_file, True)

        # Obtain <Map> projection
        self.prj = mapnik.Projection(self.m.srs)
        self.tr = mapnik.ProjTransform(map_prj, self.prj)

        # Projects between tile pixel co-ordinates and LatLong (EPSG:4326)
        self.tile_proj = GoogleProjection(max_zoom + 1, tile_size)
        self.tile_size = tile_size
        self.tile_fmt = tile_fmt

    def render_tile(self, tile_uri, x, y, z):
        # Calculate pixel positions of bottom-left & top-right
        p0 = (x * self.tile_size, (y + 1) * self.tile_size)
        p1 = ((x + 1) * self.tile_size, y * self.tile_size)

        # Convert to LatLong (EPSG:4326)
        l0 = self.tile_proj.from_pixel_to_ll(p0, z)
        l1 = self.tile_proj.from_pixel_to_ll(p1, z)

        # Bounding box for the tile
        bbox = mapnik.Box2d(l0[0], l0[1], l1[0], l1[1])

        # Convert to map projection (e.g. mercator co-ordinates EPSG:3857)
        bbox = self.tr.forward(bbox)

        self.m.zoom_to_box(bbox)
        if self.m.buffer_size < 128:
            self.m.buffer_size = 128

        # Render image with default AGG renderer
        im = mapnik.Image(self.tile_size, self.tile_size)
        mapnik.render(self.m, im)

        if self.tile_fmt == "webp":
            im.save(tile_uri, "webp:lossless=1:quality=100:image_hint=3")
        elif self.tile_fmt == "jpg":
            im.save(tile_uri, "jpeg100")
        else:
            im.save(tile_uri, self.tile_fmt + ":z=9:s=rle")

    def loop(self):
        while True:
            # Fetch a tile from the queue and render it
            r = self.q.get()
            if r is None:
                self.q.task_done()
                break

            (name, tile_uri, x, y, z) = r

            exists = ""
            if os.path.isfile(tile_uri):
                exists = "exists"
            else:
                self.render_tile(tile_uri, x, y, z)

            empty = ""
            if logger.isEnabledFor(logging.DEBUG):
                data = os.stat(tile_uri)[6]
                if data in (103, 126, 222):
                    empty = "empty"

            logger.debug(self.m.scale_denominator())
            logger.debug("(%s : %s, %s, %s, %s, %s)", name, z, x, y, exists, empty)
            self.q.task_done()


def render_tiles(
    map_file,
    map_prj,
    bbox,
    min_zoom,
    max_zoom,
    threads,
    name,
    tile_size,
    tile_fmt,
    tile_dir,
    tile_ext,
):
    logger.info(
        "render_tiles(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s %s)",
        map_file,
        map_prj,
        bbox,
        min_zoom,
        max_zoom,
        threads,
        name,
        tile_size,
        tile_fmt,
        tile_dir,
        tile_ext,
    )

    # Launch rendering threads
    queue = Queue(-1)
    renderers = {}

    for i in range(threads):
        renderer = RenderThread(queue, map_file, map_prj, max_zoom, tile_size, tile_fmt)
        render_thread = threading.Thread(target=renderer.loop)
        render_thread.start()
        logger.info("Started render thread %s", render_thread.getName())
        renderers[i] = render_thread

    if not os.path.isdir(tile_dir):
        os.mkdir(tile_dir)

    gprj = GoogleProjection(max_zoom + 1, tile_size)
    ll0 = (bbox[0], bbox[3])
    ll1 = (bbox[2], bbox[1])

    for z in range(min_zoom, max_zoom + 1):
        px0 = gprj.from_ll_to_pixel(ll0, z)
        px1 = gprj.from_ll_to_pixel(ll1, z)

        # Check if we have directories in place
        str_z = "%s" % z
        tile_sizef = float(tile_size)
        if not os.path.isdir(os.path.join(tile_dir, str_z)):
            os.mkdir(os.path.join(tile_dir, str_z))

        for x in range(int(px0[0] / tile_sizef), int(px1[0] / tile_sizef) + 1):
            # Validate x co-ordinate
            if (x < 0) or (x >= 2 ** z):
                continue

            # Check if we have directories in place
            str_x = "%s" % x
            if not os.path.isdir(os.path.join(tile_dir, str_z, str_x)):
                os.mkdir(os.path.join(tile_dir, str_z, str_x))

            for y in range(int(px0[1] / tile_sizef), int(px1[1] / tile_sizef) + 1):
                # Validate y co-ordinate
                if (y < 0) or (y >= 2 ** z):
                    continue

                # Submit tile to be rendered into the queue
                str_y = "%s" % y
                tile_uri = os.path.join(tile_dir, str_z, str_x, str_y + "." + tile_ext)
                t = (name, tile_uri, x, y, z)
                try:
                    queue.put(t)
                except KeyboardInterrupt:
                    raise SystemExit("Ctrl-C detected, exiting...")

    # Signal render threads to exit by sending empty request to queue
    for _ in range(threads):
        queue.put(None)

    # Wait for pending rendering jobs to complete
    queue.join()

    for i in range(threads):
        renderers[i].join()


if __name__ == "__main__":
    parser = ArgumentParser(
        usage="%(prog)s [options] input output 1..18 1..18",
        allow_abbrev=False,
    )
    # Positional arguments
    parser.add_argument(
        "input",
        help="mapnik XML file",
    )
    parser.add_argument(
        "output",
        help="a MBTiles file",
        default=None,
    )
    parser.add_argument(
        "min",
        help="minimum zoom level to render",
        type=int,
        metavar="1..18",
        choices=range(1, 18),
        default="1",
    )
    parser.add_argument(
        "max",
        help="maximum zoom level to render",
        type=int,
        metavar="1..18",
        choices=range(1, 18),
        default="18",
    )
    # Optional arguments
    parser.add_argument(
        "--bbox",
        help="bounding box that will be rendered",
        nargs=4,
        type=float,
        metavar="f",
    )
    parser.add_argument(
        "--threads",
        help="# of rendering threads to spawn",
        type=int,
        default=8,
    )
    parser.add_argument(
        "--name",
        help="name for each renderer",
        default="unknown",
    )
    parser.add_argument(
        "--size",
        help="resolution of the tile image",
        type=int,
        metavar="SIZE",
        choices=[1024, 512, 256],
        default=512,
    )
    # MBUtil arguments
    parser.add_argument(
        "--format",
        help="format of the image tiles",
        dest="format",
        type=str,
        metavar="FORMAT",
        choices=["jpg", "png", "png8", "png24", "png32", "png256", "webp"],
        default="png",
    )
    parser.add_argument(
        "--scheme",
        help="tiling scheme of the tiles",
        dest="scheme",
        type=str,
        metavar="SCHEME",
        choices=["xyz", "tms"],
        default="tms",
    )
    parser.add_argument(
        "--no_compression",
        help="disable MBTiles compression",
        dest="compression",
        action="store_false",
        default=True,
    )
    parser.add_argument(
        "--verbose",
        dest="silent",
        action="store_false",
        default=True,
    )

    args = parser.parse_args()
    if not args.silent:
        logging.basicConfig(level=logging.DEBUG)

    logger = logging.getLogger(__name__)
    base_dir = os.path.dirname(args.input)
    tiles_dir = os.path.join(base_dir, "tiles")
    tiles_ext = "png" if args.format.startswith("png") else args.format
    mbtiles_path = args.output
    prj = mapnik.Projection(MAPNIK_LONGLAT_PROJ)

    if os.path.exists(tiles_dir) and os.path.isdir(tiles_dir):
        shutil.rmtree(tiles_dir)

    if not args.bbox:
        args.bbox = [-180, -MERC_MAX_LATITUDE, 180, MERC_MAX_LATITUDE]
    else:
        args.bbox[0] = min(max(-180.0, args.bbox[0]), 180.0)
        args.bbox[1] = min(max(-MERC_MAX_LATITUDE, args.bbox[1]), MERC_MAX_LATITUDE)
        args.bbox[2] = min(max(-180.0, args.bbox[2]), 180.0)
        args.bbox[3] = min(max(-MERC_MAX_LATITUDE, args.bbox[3]), MERC_MAX_LATITUDE)

    render_tiles(
        args.input,
        prj,
        args.bbox,
        args.min,
        args.max,
        args.threads,
        args.name,
        args.size,
        args.format,
        tiles_dir,
        tiles_ext,
    )

    # Import `tiles` directory into a `MBTiles` file
    if mbtiles_path:
        if os.path.isfile(mbtiles_path):
            # `MBTiles` file must not already exist
            sys.stderr.write("Importing tiles into already-existing MBTiles is not yet supported\n")
            sys.exit(1)

        metadata = {
            "name": os.path.splitext(os.path.basename(mbtiles_path))[0],
            "format": tiles_ext,
            "bounds": f"{str(args.bbox[0])}, {str(args.bbox[1])}, {str(args.bbox[2])}, {str(args.bbox[3])}",
            "minzoom": str(args.min),
            "maxzoom": str(args.max),
            "attribution": "",
            "description": "",
            "type": "",
            "version": "",
        }

        metadata = {k: v for k, v in metadata.items() if v != ""}

        with open(os.path.join(tiles_dir, "metadata.json"), "w") as outfile:
            json.dump(metadata, outfile, sort_keys=True, indent=4, separators=(",", ": "))

        args.format = tiles_ext
        disk_to_mbtiles(tiles_dir, mbtiles_path, **args.__dict__)
