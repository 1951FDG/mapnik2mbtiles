# mapnik2mbtiles

Converts a Mapnik XML file into an MBTiles file.

This is used to generate tile overlays for maps, e.g. Google Maps for Android apps.

## Table of Contents

<details>
<summary>"Click to expand"</summary>

- [Installation](#installation)
- [Usage](#usage)
- [Feedback](#feedback)
- [Documentation](#documentation)
- [Credits](#credits)
- [Built with](#built-with)
- [Attributions](#attributions)
- [Acknowledgments](#acknowledgments)

</details>

## Installation

### macOS - Python 3.9

```sh
# Common dependencies
brew install gnu-sed mapnik boost-python3 py3cairo
```

```sh
# Python bindings for Mapnik
git clone --branch v3.0.x git@github.com:mapnik/python-mapnik.git
cd python-mapnik
gsed -i 's~{0}/include/pycairo~/usr/local/include/pycairo~g' setup.py
BOOST_PYTHON_LIB=boost_python39 PYCAIRO=true pip3 install .
```

```sh
# MBUtil dependency
git clone git://github.com/mapbox/mbutil.git
cd mbutil
pip3 install .
```

## Usage

```sh
output=$project/app/src/main/assets/world.mbtiles
rm -i "$output"
cd mapnik2mbtiles
python3 generate_tiles_multiprocess.py mapfile.xml "$output" 4 4 --format webp
```

```console
generate_tiles_multiprocess.py --help
usage: generate_tiles_multiprocess.py [options] input output 1..18 1..18

positional arguments:
  input             mapnik XML file
  output            a MBTiles file
  1..18             minimum zoom level to render
  1..18             maximum zoom level to render

optional arguments:
  -h, --help        show this help message and exit
  --bbox f f f f    bounding box that will be rendered
  --threads THREADS # of rendering threads to spawn
  --name NAME       name for each renderer
  --size SIZE       resolution of the tile image
  --format FORMAT   format of the image tiles
  --scheme SCHEME   tiling scheme of the tiles
  --no_compression  disable MBTiles compression
  --verbose
```

## Feedback

Feel free to send us feedback by submitting an [issue](https://github.com/1951FDG/mapnik2mbtiles/issues/new). Bug reports, feature requests, patches, and well-wishes are always welcome.

> **Note**:
> Pull requests are welcome. For major changes, please submit an issue first to discuss what you would like to change.

## Documentation

- <https://github.com/mapnik/mapnik/wiki/aspect-fix-mode>
- <https://github.com/mapnik/mapnik/wiki/image-io>
- <https://github.com/mapnik/mapnik/wiki/mapnikrenderers>
- <https://maptiler.com/google-maps-coordinates-tile-bounds-projection/>
- <https://wiki.openstreetmap.org/wiki/slippy_map_tilenames>
- <https://wiki.openstreetmap.org/wiki/zoom_levels>

## Credits

- [Old XML format Mapnik stylesheets](https://github.com/openstreetmap/mapnik-stylesheets)
    - Modified [generate_tiles_multiprocess.py](generate_tiles_multiprocess.py)

## Built with

- [TileMill](http://tilemill.s3.amazonaws.com/latest/TileMill-0.10.2.zip)

## Attributions

- [Natural Earth Map Data](https://www.naturalearthdata.com/downloads/10m-physical-vectors/)

## Acknowledgments

Special thanks to [MapBox](https://github.com/mapbox) for the [MBTiles](https://github.com/mapbox/mbtiles-spec/blob/master/1.3/spec.md) file format.
