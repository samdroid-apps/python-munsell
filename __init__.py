# Copyright (C) Sam Parkinson 2014
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Using algorithms from:
# <http://pteromys.melonisland.net/code/rainbow/munsell.py.txt>

import re
import math

from table import table


def _xyy_to_rgb_linear(x, y, y2):
    if abs(y) < 1e-100:
        y = 1e-100
    y2 /= 100
    x2 = y2 * x / y
    z2 = y2 * (1 - x - y) / y
    return (3.2406 * x2 - 1.5372 * y2 - 0.4986 * z2,
            -0.9689 * x2 + 1.8758 * y2 + 0.0415 * z2,
            0.0557 * x2 - 0.2040 * y2 + 1.0570 * z2)


def _rgb_delinearize(rgb):
    ans = [0, 0, 0]
    for i, c in enumerate(rgb):
        if c <= 0.0031308:
            ans[i] = 12.92 * c
        else:
            ans[i] = 1.055 * math.pow(c, 1 / 2.4) - 0.055
    return tuple(ans)


def _vaild_step(step):
    # Valid steps are 2.5, 5, 7.5 and 10
    step = 10 if step > 10 else (2.5 if step < 2.5 else step)
    return int(step) if int(step) == step  else step


def _find_valid_value(hue, value, chroma, direction):
    round_ = math.ceil if direction == 1 else math.floor
    value = round_(value * 5) / 5
    value = int(value) if value.is_integer() else value

    direction_changed = False
    while True:
        if value > 10 or value < 0:
            if direction_changed:
                raise NotInTableError('Trying to interpolate, but cannot find'
                                      ' a valid value attribute')
            direction *= -1
            direction_changed = True

        if '{} {} {}'.format(hue, value, chroma) in table:
            return value

        if (value > 1 and direction == 1) or (value > 2):
            value += direction
            value = int(value)
        else:
            value += 0.2 * direction
            value = round(value, 1)
            value = int(value) if value.is_integer() else value

def _closness_factors(a, b, orig):
    if a == b:
        return None, None
    else:
        total_diff = float(abs(orig - a) + abs(orig - b))
        # Oppisite of the percentage of the difference, so flip a
        # and b around
        return abs(orig - b) / total_diff, abs(orig - a) / total_diff


def _average_not_none(*values):
    not_none = [float(i) for i in values if i is not None]
    if len(not_none):
        return sum(not_none) / len(not_none)
    return 0.5


class TableNotFoundError(Exception):
    pass


class NotInTableError(Exception):
    pass


class MunsellColor(object):
    '''
    This object represents a color from the Munsell color system [1].
    It stores three values: the hue, value and chroma.

    The hue should be formatted as 'stepPRINCIPAL', eg. '5R' or '8PB'.
    Step is a float from 0 to 10.  The value ranges from 0 (black) to
    10 (white). Chroma represents the purity of the color. It is
    also a float.

    Example Usage
    =============

    >>> import munsell
    >>> c = munsell.MunsellColor('10GY', 8, 16)
    >>> c.to_rgb()
    (0.2794503352552019, 0.9074706287302171, 0.2523704238358717)
    >>> [hex(int(i * 255)) for i in c.to_rgb()]
    ['0x47', '0xe7', '0x40']

    [1] http://en.wikipedia.org/wiki/Munsell_color_system
    '''

    def __init__(self, hue, value, chroma):
        self.hue = hue
        self.value = value
        self.chroma = chroma

    def to_rgb(self):
        '''
        This converts the Munsell color to a RGB color.
        The convertion is not exact, but is quite close.

        Will return a tuple of floats if successful.
        Can raise TableNotFoundError, NotInTableError.
        '''
        if self.chroma == 0:
            return self._to_rgb_gray()

        xyY = table.get(str(self))
        if xyY is None:
            return self._to_rgb_interpolate()

        return _rgb_delinearize(_xyy_to_rgb_linear(*xyY))

    def _to_rgb_gray(self):
        v = 255 * (self.value / 10.0)
        return (v, v, v)

    def _to_rgb_interpolate(self):
        value = _find_valid_value
        mv = self.value
        step, principal = split_hue(self.hue)

        # Find the closet hue/chroma values in the table that are
        # above and below our color
        step_above = _vaild_step(math.ceil(float(step) / 2.5) * 2.5)
        ha = '{}{}'.format(step_above, principal)
        ca = max(int(math.ceil(self.chroma / 2.0) * 2), 2)

        step_below = _vaild_step(math.floor(float(step) / 2.5) * 2.5)
        hb = '{}{}'.format(step_below, principal)
        cb = max(int(math.floor(self.chroma / 2.0) * 2), 2)

        # rgb, difference factor
        a, ad = self._interpolate_munsell(
                MunsellColor(ha, value(ha, mv, ca, 1), ca),
                MunsellColor(hb, value(hb, mv, ca, 1), ca))
        b, bd = self._interpolate_munsell(
                MunsellColor(ha, value(ha, mv, ca, -1), ca),
                MunsellColor(hb, value(hb, mv, ca, -1), ca))
        c, cd = self._interpolate_munsell(
                MunsellColor(ha, value(ha, mv, cb, 1), cb),
                MunsellColor(hb, value(hb, mv, cb, 1), cb))
        d, dd = self._interpolate_munsell(
                MunsellColor(ha, value(ha, mv, cb, -1), cb),
                MunsellColor(hb, value(hb, mv, cb, -1), cb))

        e, ed = self._interpolate_rgb(a, b, ad, bd)
        f, fd = self._interpolate_rgb(c, d, cd, dd)
        return self._interpolate_rgb(f, e, ed, fd)[0]

    def _interpolate_munsell(self, a, b):
        # Generate 'closness factors' [0-1] of the a/b colors to
        # the original colors
        step = float(split_hue(self.hue)[0])
        step_a = float(split_hue(a.hue)[0])
        step_b = float(split_hue(b.hue)[0])

        hue_a, hue_b = _closness_factors(step_a, step_b, step)
        value_a, value_b = _closness_factors(a.value, b.value, self.value)
        chroma_a, chroma_b = _closness_factors(a.chroma, b.chroma, self.chroma)
        closness_a = _average_not_none(hue_a, value_a, chroma_a)
        closness_b = _average_not_none(hue_b, value_b, chroma_b)

        total_diff = abs(step - step_a) + abs(step - step_b) \
                     + abs(self.value - a.value) + abs(self.value - b.value) \
                     + abs(self.chroma - a.chroma) \
                     + abs(self.chroma - b.chroma)

        # Blend the above/below colors bases on the closness
        return tuple([a * closness_a + b * closness_b for \
                      a, b in zip(a.to_rgb(), b.to_rgb())]), total_diff

    def _interpolate_rgb(self, a, b, ad, bd):
        # Opposite of the percentage of the difference, so flip a
        # and b around
        if ad + bd == 0:
            return tuple([a * 0.5 + b * 0.5 for a, b in zip(a, b)]), 0

        if ad == 0:
            return a, 0
        if bd == 0:
            return b, 0

        a_closness = bd / (ad + bd)
        b_closness = ad / (ad + bd)
        return tuple([a * a_closness + b * b_closness for \
                      a, b in zip(a, b)]), ad + bd

    def is_real(self):
        '''
        Tests if this is a real color, by checking if it can be
        represented using RGB.
        '''
        for v in self.to_rgb():
            if v > 1.0:
                return False
        return True

    def __str__(self):
        return '{} {} {}'.format(self.hue, self.value, int(self.chroma))

def max_chroma(hue, value):
    m = 2
    while True:
        if '{} {} {}'.format(hue, value, m) in table:
            m += 2
        else:
            return m - 2

def split_hue(hue):
    return re.match('([0-9.]+)([A-Z]+)', hue).groups()
