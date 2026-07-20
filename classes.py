from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Input, Label, OptionList, Static, Button


# Testo ASCII per la schermata centrale
ASCII_ART = """
  ██████╗██╗███╗   ██╗███████╗███╗   ███╗ █████╗ 
 ██╔════╝██║████╗  ██║██╔════╝████╗ ████║██╔══██╗
 ██║     ██║██╔██╗ ██║█████╗  ██╔████╔██║███████║
 ██║     ██║██║╚██╗██║██╔══╝  ██║╚██╔╝██║██╔══██║
 ╚██████╗██║██║ ╚████║███████╗██║ ╚═╝ ██║██║  ██║
  ╚═════╝╚═╝╚═╝  ╚═══╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝
"""


class CinemaTUI(App):
    """Interfaccia Media Center stile Spotify/Spotatui."""

    CSS = """
    Screen {
        /* Creiamo una griglia: 4 colonne, 10 righe proporzionali */
        layout: grid;
        grid-size: 4 10; 
        background: black;
        color: white;
    }

    /* --- BARRA SUPERIORE --- */
    #top-bar {
        column-span: 4;
        row-span: 1;
        layout: horizontal;
    }

    #search-box {
        width: 1fr;
        border: round #61afef;
        height: 3;
    }

    .small-panel {
        width: 15;
        border: round #61afef;
        height: 3;
        content-align: center middle;
        color: #abb2bf;
    }

    /* --- COLONNA LATERALE (Liste) --- */
    #sidebar {
        column-span: 1;
        row-span: 7;
        layout: vertical;
    }

    .list-box {
        border: round #c678dd;
        height: 1fr;
        background: black;
    }

    /* --- ZONA CENTRALE --- */
    #main-content {
        column-span: 3;
        row-span: 7;
        border: round #61afef;
        padding: 1 2;
    }

    .ascii-art {
        color: #98c379;
        text-style: bold;
        margin-bottom: 2;
    }

    .info-text {
        color: #e5c07b;
    }

    /* --- BARRA INFERIORE (Player) --- */
    #player-bar {
        column-span: 4;
        row-span: 2;
        border: round #56b6c2;
        layout: vertical;
        content-align: center middle;
    }

    #controls {
        layout: horizontal;
        align: center middle;
        height: auto;
    }

    Button {
        min-width: 10;
        margin: 0 1;
        background: black;
        color: white;
        border: none;
        text-style: bold;
    }
    Button:hover {
        background: #3e4451;
    }
    """

    def compose(self) -> ComposeResult:
                
        # 1. Barra di Ricerca e Opzioni (Alto)
        with Horizontal(id="top-bar"):
            search = Input(placeholder="Cerca film o URL...")
            search.border_title = "Search"
            yield search
            
            help_btn = Static("Help\nType ?", classes="small-panel")
            help_btn.border_title = "Help"
            yield help_btn
            
            settings = Static("Settings\nType Alt+,", classes="small-panel")
            settings.border_title = "Settings"
            yield settings

        # 2. Barra Laterale (Libreria e Categorie)
        with Vertical(id="sidebar"):
            library = OptionList("Local Files", "Netflix", "YouTube", "Prime Video")
            library.border_title = "Sources"
            library.add_class("list-box")
            yield library

            playlists = OptionList("Azione", "Commedie", "Fantascienza", "Anime", "Download")
            playlists.border_title = "Categories"
            playlists.add_class("list-box")
            yield playlists

        # 3. Contenuto Principale (Centro)
        with VerticalScroll(id="main-content") as main:
            main.border_title = "Welcome!"
            yield Static(ASCII_ART, classes="ascii-art")
            yield Static("Sistema pronto.\nMotore di riproduzione mpv caricato con successo.\n\nLog located in /tmp/cinema_logs/log_1203\n", classes="info-text")
            yield Static("Changelog\n\n== [v1.0.0] Inizializzazione ==\n- Aggiunto supporto Kiosk DRM\n- Interfaccia TUI completata")

        # 4. Barra del Player (Basso)
        with Vertical(id="player-bar") as pbar:
            pbar.border_title = "Ready ( MP4 Locale | Nessun media in riproduzione )"
            with Horizontal(id="controls"):
                yield Button("[Prev]", id="prev")
                yield Button("[Play/Pause]", id="play")
                yield Button("[Next]", id="next")
                yield Button("[Stop]", id="stop")
                yield Button("[Vol-]", id="voldown")
                yield Button("[Vol+]", id="volup")
