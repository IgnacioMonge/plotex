"""Preserve pixels and painter state when sharing recorded marker paths."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest


@pytest.fixture
def painting(qapp):
    from veusz import qtall as qt, utils
    from veusz.helpers.recordpaint import RecordPaintDevice
    return qt, utils, RecordPaintDevice


def make_image(qt):
    image = qt.QImage(180, 160, qt.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(qt.QColor("white"))
    return image


def draw_markers(qt, utils, painter, marker, scaling, colored, scaleline):
    painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
    painter.translate(3.5, 2.5)
    painter.setClipRect(qt.QRectF(5., 6., 152., 137.))
    painter.setPen(qt.QPen(qt.QColor(10, 30, 70, 190), 1.3))
    painter.setBrush(qt.QBrush(qt.QColor(25, 170, 210, 150)))
    x = np.linspace(-5., 175., 35)
    y = 70. + 45. * np.sin(x / 12.)
    # Include duplicates and points outside the clip.
    x[12:15], y[12:15] = x[11], y[11]
    factors = np.linspace(.3, 2., len(x)) if scaling else None
    colors = np.linspace(0., 1., len(x)) if colored else None
    cmap = ((0, 0, 255, 255), (255, 150, 0, 120))
    utils.plotMarkers(painter, x, y, marker, 4., scaling=factors,
                      clip=qt.QRectF(5., 6., 152., 137.),
                      cmap=cmap, colorvals=colors, scaleline=scaleline)
    # The next primitive must retain the brush, pen and transform.
    painter.drawLine(qt.QPointF(15., 135.), qt.QPointF(120., 132.))


@pytest.mark.parametrize("marker", ["circle", "cross", "diamond"])
@pytest.mark.parametrize("scaling,colored,scaleline", [
    (False, False, False), (False, True, False),
    (True, True, False), (True, True, True)])
def test_recorded_markers_match_direct_pixels(painting, marker, scaling, colored, scaleline):
    qt, utils, RecordPaintDevice = painting
    direct = make_image(qt)
    painter = qt.QPainter(direct)
    draw_markers(qt, utils, painter, marker, scaling, colored, scaleline)
    painter.end()

    record = RecordPaintDevice(180, 160, 100, 100)
    painter = qt.QPainter(record)
    draw_markers(qt, utils, painter, marker, scaling, colored, scaleline)
    painter.end()
    replay = make_image(qt)
    painter = qt.QPainter(replay)
    record.play(painter)
    painter.end()
    assert direct == replay


def test_recorded_path_retains_geometry_after_original_changes(painting):
    qt, _, RecordPaintDevice = painting

    def draw(painter):
        painter.setBrush(qt.QColor("blue"))
        path = qt.QPainterPath()
        path.addEllipse(qt.QRectF(10, 10, 15, 15))
        painter.drawPath(path)
        painter.translate(30, 0)
        painter.drawPath(path)
        path.addRect(qt.QRectF(10, 30, 20, 20))
        painter.drawPath(path)
        painter.translate(30, 0)
        painter.drawPath(path)

    direct = make_image(qt)
    painter = qt.QPainter(direct)
    draw(painter)
    painter.end()
    record = RecordPaintDevice(180, 160, 100, 100)
    painter = qt.QPainter(record)
    draw(painter)
    painter.end()

    def replay(_):
        image = make_image(qt)
        painter = qt.QPainter(image)
        record.play(painter)
        painter.end()
        return image

    with ThreadPoolExecutor(max_workers=2) as pool:
        images = list(pool.map(replay, range(8)))
    assert all(image == direct for image in images)
