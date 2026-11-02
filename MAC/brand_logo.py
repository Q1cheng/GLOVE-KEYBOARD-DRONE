"""Resolution-independent contours of the approved drone-logo-source.png."""

import json
import math
from functools import lru_cache
from pathlib import Path

from AppKit import NSApplication, NSBezierPath, NSColor, NSGraphicsContext, NSMakeRect, NSView


@lru_cache(maxsize=1)
def logo_paths():
    source = Path(__file__).with_name("assets") / "drone-logo-paths.json"
    return json.loads(source.read_text())


def transformed_points(points, size, x, y, angle=0):
    cosine, sine = math.cos(angle)*size, math.sin(angle)*size
    return [(x+px*cosine-py*sine, y+px*sine+py*cosine) for px, py in points]


def _color(value):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(
        *(int(value[i:i+2], 16)/255 for i in (1, 3, 5)), 1)


class _LogoView(NSView):
    def isFlipped(self):
        return True

    def isOpaque(self):
        return False

    def hitTest_(self, point):
        return None

    def drawRect_(self, rect):
        NSGraphicsContext.currentContext().setShouldAntialias_(True)
        for points, color in self.contours:
            path = NSBezierPath.bezierPath()
            path.moveToPoint_(points[0])
            for point in points[1:]:
                path.lineToPoint_(point)
            path.closePath()
            color.setFill()
            path.fill()


class BrandLogo:
    def __init__(self, canvas, size, color, background):
        self.canvas = canvas
        self.size = size
        self.paths = logo_paths()
        self.colors = [_color(background if path["hole"] else color) for path in self.paths]
        self.view = None
        self.closed = False
        self.position = (0, 0)
        self.angle = 0
        self.bounds = math.ceil(size*1.5)+2
        canvas.bind("<Configure>", self._position, add="+")
        canvas.bind("<Destroy>", self._close, add="+")
        self.job = canvas.after_idle(self._attach)

    def _attach(self):
        if self.closed:
            return
        title = self.canvas.winfo_toplevel().title()
        window = next((w for w in NSApplication.sharedApplication().windows()
                       if w.title() == title), None)
        if window is None:
            self.job = self.canvas.after(16, self._attach)
            return
        self.content = window.contentView()
        self.view = _LogoView.alloc().initWithFrame_(NSMakeRect(0, 0, self.bounds, self.bounds))
        self.view.contours = []
        self.content.addSubview_(self.view)
        self.draw(*self.position, angle=self.angle)

    def _position(self, event=None):
        if self.closed or self.view is None:
            return
        root = self.canvas.winfo_toplevel()
        x = self.canvas.winfo_rootx()-root.winfo_rootx()+self.position[0]-self.bounds/2
        y = self.canvas.winfo_rooty()-root.winfo_rooty()+self.position[1]+self.bounds/2
        self.view.setFrame_(NSMakeRect(x, self.content.bounds().size.height-y,
                                       self.bounds, self.bounds))

    def draw(self, x, y, angle=0):
        self.position, self.angle = (x, y), angle
        if self.view is None or self.closed:
            return
        self.view.contours = [(transformed_points(path["points"], self.size,
                              self.bounds/2, self.bounds/2, angle), color)
                              for path, color in zip(self.paths, self.colors)]
        self._position()
        self.view.setNeedsDisplay_(True)

    def _close(self, event):
        if event.widget is not self.canvas:
            return
        self.closed = True
        self.canvas.after_cancel(self.job)
        if self.view is not None:
            self.view.removeFromSuperview()
