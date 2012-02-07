"""
Package-private module :mod:`nhe.geo._utils` contains functions that are
common to several geographical primitives.
"""
import numpy
import pyproj
import shapely.geometry

#: Geod object to be used whenever we need to deal with
#: spherical coordinates.
GEOD = pyproj.Geod(ellps='sphere')


def clean_points(points):
    """
    Given a list of :class:`~nhe.geo.point.Point` objects, return a new list
    with adjacent duplicate points removed.

    >>> from nhe.geo import Point
    >>> a, b, c = Point(1, 2, 3), Point(3, 4, 5), Point(5, 6, 7)
    >>> _clean_points([a, a, a, b, a, c, c]) == [a, b, a, c]
    True
    >>> a, b, c = Point(1e-4, 1e-4), Point(0, 0), Point(1e-5, 1e-5)
    >>> _clean_points([a, b, c]) == [a, b]
    True
    """
    if not points:
        return points

    result = [points[0]]
    for point in points:
        if point != result[-1]:
            result.append(point)
    return result


def line_intersects_itself(lons, lats, closed_shape=False):
    """
    Return ``True`` if line of points intersects itself.
    Line with the last point repeating the first one considered
    intersecting itself.

    The line is defined by lists (or numpy arrays) of points'
    longitudes and latitudes (depth is not taken into account).

    :param closed_shape:
        If ``True`` the line will be checked twice: first time with its
        original shape and second time with the points sequence being
        shifted by one point (the last point becomes first, the first
        turns second and so on). This is useful for checking that
        the sequence of points defines a valid :class:`Polygon`.
    """
    assert len(lons) == len(lats)

    if len(lons) <= 3:
        # line can not intersect itself unless there are
        # at least four points
        return False

    west, east, north, south = get_spherical_bounding_box(lons, lats)
    proj = get_stereographic_projection(west, east, north, south)

    xx, yy = proj(lons, lats)
    if not shapely.geometry.LineString(zip(xx, yy)).is_simple:
        return True

    if closed_shape:
        xx, yy = proj(numpy.roll(lons, 1), numpy.roll(lats, 1))
        if not shapely.geometry.LineString(zip(xx, yy)).is_simple:
            return True

    return False


def get_longitudinal_extent(lon1, lon2):
    """
    Return the distance between two longitude values as an angular measure.
    Parameters represent two longitude values in degrees.

    :return:
        Float, the angle between ``lon1`` and ``lon2`` in degrees. Value
        is positive if ``lon2`` is on the east from ``lon1`` and negative
        otherwise. Absolute value of the result doesn't exceed 180 for
        valid parameters values.

    >>> get_longitudinal_extent(10, 20)
    10
    >>> get_longitudinal_extent(20, 10)
    -10
    >>> get_longitudinal_extent(-10, -15)
    -5
    >>> get_longitudinal_extent(-120, 30)
    150
    >>> get_longitudinal_extent(-178.3, 177.7)
    -4.0
    >>> get_longitudinal_extent(178.3, -177.7)
    4.0
    >>> get_longitudinal_extent(95, -180 + 94)
    179
    >>> get_longitudinal_extent(95, -180 + 96)
    -179
    """
    extent = lon2 - lon1
    if extent > 180:
        extent = -360 + extent
    elif extent < -180:
        extent = 360 + extent
    return extent


def get_spherical_bounding_box(lons, lats):
    """
    Given a collection of points find and return the bounding box,
    as a pair of longitudes and a pair of latitudes.

    Parameters define longitudes and latitudes of a point collection
    respectively in a form of lists or numpy arrays.

    :return:
        A tuple of four items. These items represent western, eastern,
        northern and southern borders of the bounding box respectively.
        Values are floats in decimal degrees.
    :raises RuntimeError:
        If points collection has the longitudinal extent of more than
        180 degrees (it is impossible to define a single hemisphere
        bound to poles that would contain the whole collection).

    >>> gsbb = get_spherical_bounding_box; gsbb([10, -10], [50, 60])
    (-10, 10, 60, 50)
    >>> gsbb([20], [-40])
    (20, 20, -40, -40)
    >>> gsbb([-20, 180, 179, 178], [-1, -2, 1, 2])
    (178, -20, 2, -2)

    >>> gsbb([-45, -135, 135, 45], [80] * 4)
    Traceback (most recent call last):
        ...
    RuntimeError: points collection has longitudinal extent wider than 180 deg

    >>> gsbb([0, 10, -175], [0, 0, 0])
    Traceback (most recent call last):
        ...
    RuntimeError: points collection has longitudinal extent wider than 180 deg
    """
    north, south = numpy.max(lats), numpy.min(lats)
    west, east = numpy.min(lons), numpy.max(lons)
    assert (-180 < west <= 180) and (-180 < east <= 180)
    if get_longitudinal_extent(west, east) < 0:
        # points are lying on both sides of the international date line
        # (meridian 180). the actual west longitude is the lowest positive
        # longitude and east one is the highest negative.
        west = min(lon for lon in lons if lon > 0)
        east = max(lon for lon in lons if lon < 0)
        if not all ((get_longitudinal_extent(west, lon) >= 0
                     and get_longitudinal_extent(lon, east) >= 0)
                    for lon in lons):
            raise RuntimeError('points collection has longitudinal extent '
                               'wider than 180 deg')
    return west, east, north, south


def get_stereographic_projection(west, east, north, south):
    """
    Create and return a projection object for a given bounding box.

    Parameters define a bounding box in a spherical coordinates of the
    collection of points that is about to be projected. The center point
    of the projection (coordinates (0, 0) in Cartesian space) is set
    to the middle point of that bounding box. The resulting projection
    is defined for spherical coordinates that are not further from the
    bounding box center than 90 degree on the great circle arc.

    The result projection is of type Oblique Stereographic, see
    http://www.remotesensing.org/geotiff/proj_list/oblique_stereographic.html.

    This projection is prone to distance, area and angle distortions
    everywhere outside of the center point, but still can be used for
    checking shapes: verifying if line intersects itself (like in
    :func:`_line_intersects_itself`) or if point is inside of a polygon
    (like in :meth:`Polygon.discretize`).

    >>> t = lambda *co: sorted(get_stereographic_projection(*co).srs.split())
    >>> t(10, 16, -20, 30)
    ['+lat_0=5.0', '+lon_0=13.0', '+proj=stere', '+units=m']
    >>> t(-20, 40, 55, 56)
    ['+lat_0=55.5', '+lon_0=10.0', '+proj=stere', '+units=m']
    >>> t(177.6, -175.8, -10, 10)
    ['+lat_0=0.0', '+lon_0=-179.1', '+proj=stere', '+units=m']
    """
    middle_lat = (north + south) / 2.0
    middle_lon = west + get_longitudinal_extent(west, east) / 2.0
    if middle_lon > 180:
        middle_lon = middle_lon - 360
    return pyproj.Proj(proj='stere', lat_0=middle_lat, lon_0=middle_lon)