"""CSS Styles and visual constants for CinemaTUI."""

# ASCII Art Logo for Main Screen
ASCII_ART = r"""
   ____ ___ _   _ _____  __  __    _
  / ___|_ _| \ | | ____||  \/  |  / \
 | |    | ||  \| |  _|  | |\/| | / _ \
 | |___ | || |\  | |___ | |  | |/ ___ \
  \____|___|_| \_|_____||_|  |_/_/   \_\
"""

# Application CSS Stylesheet
APP_CSS = """
Screen {
    /* Grid system: 4 columns, 10 proportional rows */
    layout: grid;
    grid-size: 4 10; 
    background: black;
    color: white;
}

/* --- TOP NAVIGATION BAR --- */
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

/* --- SIDEBAR LISTS --- */
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

/* --- DIRECTORY TREE (Sources panel) --- */
#sources-list {
    border: round #c678dd;
    height: 1fr;
    background: black;
    scrollbar-color: #c678dd black;
}

DirectoryTree > .directory-tree--folder {
    color: #61afef;
    text-style: bold;
}

DirectoryTree > .directory-tree--file {
    color: #abb2bf;
}

DirectoryTree > .directory-tree--extension {
    color: #98c379;
}

/* --- MAIN CONTENT AREA --- */
#main-content {
    column-span: 3;
    row-span: 7;
    border: round #61afef;
    padding: 1 2;
}

#terminal-output {
    border: round #98c379;
    height: 1fr;
    background: #1e1e1e;
    margin: 1 0;
}

.ascii-art {
    color: #98c379;
    text-style: bold;
    margin-bottom: 2;
}

.info-text {
    color: #e5c07b;
}

/* --- PLAYER CONTROL BAR --- */
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
