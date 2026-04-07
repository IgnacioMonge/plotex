##############################################################################
"""Plot theme presets inspired by ggplot2.

Each theme applies a consistent visual style to all graph elements:
page, graph background/border, axes, grid, ticks, tick labels,
axis labels, legend, colorbar, text labels, error bars.
"""

from .. import document

# ── Shared setting blocks ────────────────────────────────────────

def _light_axes(line_w='0.5pt', tick_w='0.5pt', major_len='6pt',
                minor_len='3pt', mirror=False, outer=False):
    """Common axis settings for light themes."""
    return {
        'axis/Line/color': 'black',
        'axis/Line/width': line_w,
        'axis/Line/hide': False,
        'axis/autoMirror': mirror,
        'axis/outerticks': outer,
        'axis/MajorTicks/color': 'black',
        'axis/MajorTicks/width': tick_w,
        'axis/MajorTicks/length': major_len,
        'axis/MajorTicks/hide': False,
        'axis/MinorTicks/color': 'black',
        'axis/MinorTicks/width': tick_w,
        'axis/MinorTicks/length': minor_len,
        'axis/MinorTicks/hide': False,
        'axis/Label/color': 'black',
        'axis/TickLabels/color': 'black',
        # colorbar inherits from axis, but set explicitly
        'colorbar/Line/color': 'black',
        'colorbar/Label/color': 'black',
        'colorbar/TickLabels/color': 'black',
        'colorbar/MajorTicks/color': 'black',
        'colorbar/MinorTicks/color': 'black',
        'colorbar/Border/color': 'black',
    }

def _dark_axes():
    """Common axis settings for dark theme."""
    fg = '#aaaaaa'
    return {
        'axis/Line/color': fg,
        'axis/Line/width': '0.5pt',
        'axis/Line/hide': False,
        'axis/autoMirror': False,
        'axis/outerticks': False,
        'axis/MajorTicks/color': fg,
        'axis/MajorTicks/length': '6pt',
        'axis/MajorTicks/hide': False,
        'axis/MinorTicks/color': '#888888',
        'axis/MinorTicks/length': '3pt',
        'axis/MinorTicks/hide': False,
        'axis/Label/color': '#cccccc',
        'axis/TickLabels/color': '#cccccc',
        'colorbar/Line/color': fg,
        'colorbar/Label/color': '#cccccc',
        'colorbar/TickLabels/color': '#cccccc',
        'colorbar/MajorTicks/color': fg,
        'colorbar/MinorTicks/color': '#888888',
        'colorbar/Border/color': '#555555',
    }

def _light_text():
    """Text colors for light themes."""
    return {
        'Font/font': 'Arial',
        'Font/size': '11pt',
        'Font/color': 'black',
        'label/Text/color': 'black',
        'xy/ErrorBarLine/color': 'black',
    }

def _dark_text():
    """Text colors for dark theme."""
    return {
        'Font/font': 'Arial',
        'Font/size': '11pt',
        'Font/color': '#cccccc',
        'label/Text/color': '#cccccc',
        'xy/ErrorBarLine/color': '#aaaaaa',
    }

# ── Theme definitions ────────────────────────────────────────────

THEMES = {
    'classic': {
        'name': 'Classic',
        'descr': 'White background, L-shaped axes, no grid. '
                 'Standard for Nature, Cell, Science.',
        'settings': {
            **{  # Page + Graph
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': 'white',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **_light_axes(mirror=False),
            **{  # Grid off
                'axis/GridLines/hide': True,
                'axis/MinorGridLines/hide': True,
            },
            **{  # Legend
                'key/Background/color': 'white',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/color': 'black',
                'key/Border/width': '0.5pt',
                'key/Border/hide': False,
                'key/Text/color': 'black',
            },
            **_light_text(),
        },
    },

    'bw': {
        'name': 'Black & White',
        'descr': 'White background, gray grid, black border. '
                 'Clean general-purpose scientific style.',
        'settings': {
            **{
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': 'white',
                'graph/Background/hide': False,
                'graph/Border/color': 'black',
                'graph/Border/width': '0.5pt',
                'graph/Border/hide': False,
            },
            **_light_axes(mirror=True),
            **{  # Grid on, gray
                'axis/GridLines/hide': False,
                'axis/GridLines/color': '#cccccc',
                'axis/GridLines/width': '0.5pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': True,
            },
            **{
                'key/Background/color': 'white',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/color': '#888888',
                'key/Border/width': '0.5pt',
                'key/Border/hide': False,
                'key/Text/color': 'black',
            },
            **_light_text(),
        },
    },

    'pubr': {
        'name': 'Publication',
        'descr': 'Optimized for biomedical journals (NEJM, Lancet, '
                 'JAMA). Thick axes, ticks outside, no grid.',
        'settings': {
            **{
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': 'white',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **_light_axes(line_w='1pt', tick_w='1pt',
                          major_len='7pt', minor_len='4pt',
                          mirror=False, outer=True),
            **{
                'axis/GridLines/hide': True,
                'axis/MinorGridLines/hide': True,
            },
            **{
                'key/Background/color': 'white',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/hide': True,
                'key/Text/color': 'black',
            },
            **_light_text(),
            'Font/size': '12pt',
        },
    },

    'minimal': {
        'name': 'Minimal',
        'descr': 'Clean, minimal style for presentations. '
                 'No border, light grid, no axis lines.',
        'settings': {
            **{
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': 'white',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **{  # Axes hidden, only grid visible
                'axis/Line/hide': True,
                'axis/autoMirror': False,
                'axis/outerticks': False,
                'axis/MajorTicks/hide': True,
                'axis/MinorTicks/hide': True,
                'axis/GridLines/hide': False,
                'axis/GridLines/color': '#e0e0e0',
                'axis/GridLines/width': '0.5pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': True,
                'axis/Label/color': '#333333',
                'axis/TickLabels/color': '#555555',
                'colorbar/Line/color': '#999999',
                'colorbar/Label/color': '#333333',
                'colorbar/TickLabels/color': '#555555',
                'colorbar/MajorTicks/color': '#999999',
                'colorbar/MinorTicks/color': '#bbbbbb',
                'colorbar/Border/color': '#cccccc',
            },
            **{
                'key/Background/color': 'white',
                'key/Background/hide': False,
                'key/Background/transparency': 30,
                'key/Border/hide': True,
                'key/Text/color': '#333333',
            },
            'Font/font': 'Arial',
            'Font/size': '11pt',
            'Font/color': '#333333',
            'label/Text/color': '#333333',
            'xy/ErrorBarLine/color': '#666666',
        },
    },

    'dark': {
        'name': 'Dark',
        'descr': 'Dark background for screen presentations and posters.',
        'settings': {
            **{
                'page/Background/color': '#1a1a1a',
                'page/Background/hide': False,
                'graph/Background/color': '#2d2d2d',
                'graph/Background/hide': False,
                'graph/Border/color': '#555555',
                'graph/Border/width': '0.5pt',
                'graph/Border/hide': False,
            },
            **_dark_axes(),
            **{
                'axis/GridLines/hide': False,
                'axis/GridLines/color': '#444444',
                'axis/GridLines/width': '0.5pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': True,
            },
            **{
                'key/Background/color': '#3d3d3d',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/color': '#555555',
                'key/Border/width': '0.5pt',
                'key/Border/hide': False,
                'key/Text/color': '#cccccc',
            },
            **_dark_text(),
        },
    },

    # ── Styles based on published journal/software conventions ────

    'ggplot2': {
        'name': 'ggplot2',
        'descr': 'R ggplot2 default: gray panel, white grid, no border. '
                 'Wickham, H. ggplot2: Elegant Graphics for Data Analysis.',
        'settings': {
            **{
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': '#ebebeb',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **{
                'axis/Line/hide': True,
                'axis/autoMirror': False,
                'axis/outerticks': False,
                'axis/MajorTicks/hide': True,
                'axis/MinorTicks/hide': True,
                'axis/GridLines/hide': False,
                'axis/GridLines/color': 'white',
                'axis/GridLines/width': '0.75pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': False,
                'axis/MinorGridLines/color': '#f0f0f0',
                'axis/MinorGridLines/width': '0.5pt',
                'axis/MinorGridLines/style': 'solid',
                'axis/Label/color': '#333333',
                'axis/TickLabels/color': '#666666',
                'colorbar/Line/color': '#333333',
                'colorbar/Label/color': '#333333',
                'colorbar/TickLabels/color': '#666666',
                'colorbar/MajorTicks/color': '#999999',
                'colorbar/MinorTicks/color': '#bbbbbb',
                'colorbar/Border/color': '#cccccc',
            },
            **{
                'key/Background/color': '#ebebeb',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/hide': True,
                'key/Text/color': '#333333',
            },
            'Font/font': 'Arial',
            'Font/size': '11pt',
            'Font/color': '#333333',
            'label/Text/color': '#333333',
            'xy/ErrorBarLine/color': '#636363',
        },
    },

    'seaborn': {
        'name': 'Seaborn',
        'descr': 'Python seaborn "whitegrid": white background, subtle gray grid. '
                 'Waskom, M. seaborn: statistical data visualization.',
        'settings': {
            **{
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': '#eaeaf2',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **{
                'axis/Line/hide': True,
                'axis/autoMirror': False,
                'axis/outerticks': False,
                'axis/MajorTicks/hide': True,
                'axis/MinorTicks/hide': True,
                'axis/GridLines/hide': False,
                'axis/GridLines/color': 'white',
                'axis/GridLines/width': '1pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': True,
                'axis/Label/color': '#333333',
                'axis/TickLabels/color': '#333333',
                'colorbar/Line/color': '#333333',
                'colorbar/Label/color': '#333333',
                'colorbar/TickLabels/color': '#333333',
                'colorbar/MajorTicks/color': '#999999',
                'colorbar/MinorTicks/color': '#bbbbbb',
                'colorbar/Border/color': '#cccccc',
            },
            **{
                'key/Background/color': 'white',
                'key/Background/hide': False,
                'key/Background/transparency': 20,
                'key/Border/hide': True,
                'key/Text/color': '#333333',
            },
            'Font/font': 'DejaVu Sans',
            'Font/size': '11pt',
            'Font/color': '#333333',
            'label/Text/color': '#333333',
            'xy/ErrorBarLine/color': '#4c4c4c',
        },
    },

    'economist': {
        'name': 'The Economist',
        'descr': 'The Economist magazine style: blue-gray panel, '
                 'horizontal grid only, bold headers.',
        'settings': {
            **{
                'page/Background/color': '#d5e4eb',
                'page/Background/hide': False,
                'graph/Background/color': '#d5e4eb',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **{
                'axis/Line/color': '#333333',
                'axis/Line/width': '0.5pt',
                'axis/Line/hide': True,
                'axis/autoMirror': False,
                'axis/outerticks': False,
                'axis/MajorTicks/hide': True,
                'axis/MinorTicks/hide': True,
                'axis/GridLines/hide': False,
                'axis/GridLines/color': 'white',
                'axis/GridLines/width': '0.75pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': True,
                'axis/Label/color': '#333333',
                'axis/TickLabels/color': '#333333',
                'colorbar/Line/color': '#333333',
                'colorbar/Label/color': '#333333',
                'colorbar/TickLabels/color': '#333333',
                'colorbar/MajorTicks/color': '#666666',
                'colorbar/MinorTicks/color': '#999999',
                'colorbar/Border/color': '#aaaaaa',
            },
            **{
                'key/Background/color': '#d5e4eb',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/hide': True,
                'key/Text/color': '#333333',
            },
            'Font/font': 'Arial',
            'Font/size': '10pt',
            'Font/color': '#333333',
            'label/Text/color': '#333333',
            'xy/ErrorBarLine/color': '#555555',
        },
    },

    'fivethirtyeight': {
        'name': 'FiveThirtyEight',
        'descr': 'FiveThirtyEight (538) blog style: light gray background, '
                 'no axes, thick grid lines.',
        'settings': {
            **{
                'page/Background/color': '#f0f0f0',
                'page/Background/hide': False,
                'graph/Background/color': '#f0f0f0',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **{
                'axis/Line/hide': True,
                'axis/autoMirror': False,
                'axis/outerticks': False,
                'axis/MajorTicks/hide': True,
                'axis/MinorTicks/hide': True,
                'axis/GridLines/hide': False,
                'axis/GridLines/color': '#cccccc',
                'axis/GridLines/width': '1pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': True,
                'axis/Label/color': '#333333',
                'axis/TickLabels/color': '#555555',
                'colorbar/Line/color': '#555555',
                'colorbar/Label/color': '#333333',
                'colorbar/TickLabels/color': '#555555',
                'colorbar/MajorTicks/color': '#999999',
                'colorbar/MinorTicks/color': '#cccccc',
                'colorbar/Border/color': '#cccccc',
            },
            **{
                'key/Background/hide': True,
                'key/Border/hide': True,
                'key/Text/color': '#333333',
            },
            'Font/font': 'Arial',
            'Font/size': '12pt',
            'Font/color': '#333333',
            'label/Text/color': '#333333',
            'xy/ErrorBarLine/color': '#888888',
        },
    },

    'tufte': {
        'name': 'Tufte',
        'descr': 'Edward Tufte style: maximum data-ink ratio. '
                 'No grid, no border, range axes only. '
                 'Tufte, E. The Visual Display of Quantitative Information.',
        'settings': {
            **{
                'page/Background/color': '#fffff8',
                'page/Background/hide': False,
                'graph/Background/color': '#fffff8',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **{
                'axis/Line/color': '#333333',
                'axis/Line/width': '0.5pt',
                'axis/Line/hide': False,
                'axis/autoMirror': False,
                'axis/outerticks': True,
                'axis/MajorTicks/color': '#333333',
                'axis/MajorTicks/width': '0.5pt',
                'axis/MajorTicks/length': '5pt',
                'axis/MajorTicks/hide': False,
                'axis/MinorTicks/hide': True,
                'axis/GridLines/hide': True,
                'axis/MinorGridLines/hide': True,
                'axis/Label/color': '#333333',
                'axis/TickLabels/color': '#333333',
                'colorbar/Line/color': '#333333',
                'colorbar/Label/color': '#333333',
                'colorbar/TickLabels/color': '#333333',
                'colorbar/MajorTicks/color': '#333333',
                'colorbar/MinorTicks/color': '#666666',
                'colorbar/Border/color': '#999999',
            },
            **{
                'key/Background/hide': True,
                'key/Border/hide': True,
                'key/Text/color': '#333333',
            },
            'Font/font': 'Palatino Linotype',
            'Font/size': '11pt',
            'Font/color': '#333333',
            'label/Text/color': '#333333',
            'xy/ErrorBarLine/color': '#666666',
        },
    },

    'bmj': {
        'name': 'BMJ',
        'descr': 'British Medical Journal style: clean, high contrast, '
                 'box axes with ticks inside. '
                 'BMJ Author Guidelines.',
        'settings': {
            **{
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': 'white',
                'graph/Background/hide': False,
                'graph/Border/color': 'black',
                'graph/Border/width': '0.75pt',
                'graph/Border/hide': False,
            },
            **_light_axes(line_w='0.75pt', tick_w='0.75pt',
                          major_len='5pt', minor_len='3pt',
                          mirror=True, outer=False),
            **{
                'axis/GridLines/hide': True,
                'axis/MinorGridLines/hide': True,
            },
            **{
                'key/Background/color': 'white',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/hide': True,
                'key/Text/color': 'black',
            },
            'Font/font': 'Arial',
            'Font/size': '10pt',
            'Font/color': 'black',
            'label/Text/color': 'black',
            'xy/ErrorBarLine/color': 'black',
        },
    },

    'prism': {
        'name': 'GraphPad Prism',
        'descr': 'GraphPad Prism default style: L-shaped axes with ticks '
                 'outside, no grid, no border. Standard in biomedical research.',
        'settings': {
            **{
                'page/Background/color': 'white',
                'page/Background/hide': False,
                'graph/Background/color': 'white',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **_light_axes(line_w='1pt', tick_w='1pt',
                          major_len='8pt', minor_len='4pt',
                          mirror=False, outer=True),
            **{
                'axis/GridLines/hide': True,
                'axis/MinorGridLines/hide': True,
            },
            **{
                'key/Background/hide': True,
                'key/Border/hide': True,
                'key/Text/color': 'black',
            },
            'Font/font': 'Arial',
            'Font/size': '14pt',
            'Font/color': 'black',
            'label/Text/color': 'black',
            'xy/ErrorBarLine/color': 'black',
        },
    },

    'solarized': {
        'name': 'Solarized Light',
        'descr': 'Ethan Schoonover Solarized palette: '
                 'low-contrast, eye-friendly colors for extended viewing.',
        'settings': {
            **{
                'page/Background/color': '#fdf6e3',
                'page/Background/hide': False,
                'graph/Background/color': '#eee8d5',
                'graph/Background/hide': False,
                'graph/Border/hide': True,
            },
            **{
                'axis/Line/color': '#586e75',
                'axis/Line/width': '0.5pt',
                'axis/Line/hide': False,
                'axis/autoMirror': False,
                'axis/outerticks': False,
                'axis/MajorTicks/color': '#586e75',
                'axis/MajorTicks/width': '0.5pt',
                'axis/MajorTicks/length': '5pt',
                'axis/MajorTicks/hide': False,
                'axis/MinorTicks/color': '#93a1a1',
                'axis/MinorTicks/length': '3pt',
                'axis/MinorTicks/hide': True,
                'axis/GridLines/hide': False,
                'axis/GridLines/color': '#fdf6e3',
                'axis/GridLines/width': '0.5pt',
                'axis/GridLines/style': 'solid',
                'axis/MinorGridLines/hide': True,
                'axis/Label/color': '#073642',
                'axis/TickLabels/color': '#586e75',
                'colorbar/Line/color': '#586e75',
                'colorbar/Label/color': '#073642',
                'colorbar/TickLabels/color': '#586e75',
                'colorbar/MajorTicks/color': '#586e75',
                'colorbar/MinorTicks/color': '#93a1a1',
                'colorbar/Border/color': '#93a1a1',
            },
            **{
                'key/Background/color': '#eee8d5',
                'key/Background/hide': False,
                'key/Background/transparency': 0,
                'key/Border/hide': True,
                'key/Text/color': '#073642',
            },
            'Font/font': 'Inconsolata',
            'Font/size': '11pt',
            'Font/color': '#073642',
            'label/Text/color': '#073642',
            'xy/ErrorBarLine/color': '#657b83',
        },
    },
}


def applyTheme(doc, theme_key):
    """Apply a plot theme to the document's StyleSheet."""

    if theme_key not in THEMES:
        return

    theme = THEMES[theme_key]
    ops = []

    for path_suffix, value in theme['settings'].items():
        full_path = '/StyleSheet/' + path_suffix
        try:
            setn = doc.resolveSettingPath(None, full_path)
            ops.append(
                document.OperationSettingSet(setn, value))
        except (ValueError, KeyError):
            pass

    if ops:
        doc.applyOperation(
            document.OperationMultiple(
                ops, descr='apply plot theme: %s' % theme_key))


def getThemeNames():
    """Return list of (key, display_name, description) tuples."""
    return [
        (key, theme['name'], theme['descr'])
        for key, theme in THEMES.items()
    ]
