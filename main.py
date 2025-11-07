from nicegui import ui, app
from server.app_config import BASE_DIR

# Import API module so routes are registered
import server.api_endpoints  # noqa: F401

"""
Main entrypoint for the Pisa map app.
Input: none (run directly).
Output: serves UI and JSON APIs.
"""


@ui.page('/')
def index():
    """
    Render main page with embedded map iframe.
    Input: none.
    Output: HTML page with iframe to map_deck.html.
    """
    ui.add_head_html(
        '''
        <style>
          .nicegui-content {
            display: block !important;
            padding: 0 !important;
            gap: 0 !important;
            align-items: stretch !important;
          }
          #map_iframe {
            display: block;
            width: 100%;
            height: 100%;
            border: 0;
          }
        </style>
        '''
    )

    iframe_src = '/static/map_deck.html'

    with ui.card().classes(
        'map-card col-span-2 md:col-span-4 h-[88vh] overflow-hidden '
        'rounded-xl relative !p-0 !gap-0 !items-stretch'
    ):
        ui.html(
            f'<iframe id="map_iframe" src="{iframe_src}" class="w-full h-full"></iframe>',
            sanitize=False,
        ).classes('w-full h-full block')


app.add_static_files('/static', str(BASE_DIR / 'static'))

if __name__ in {'__main__', '__mp_main__'}:
    app.add_static_files('/static', str(BASE_DIR / 'static'))
    ui.run(title='Pisa Map', port=8080)
