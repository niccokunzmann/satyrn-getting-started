"""Sphinx configuration of the documentation site (published on GitHub Pages)."""

project = "Local code generation"
author = "satyrn-getting-started contributors"
project_copyright = f"2026, {author}"

REPOSITORY = "https://github.com/niccokunzmann/satyrn-getting-started"

extensions = ["myst_parser", "sphinx_copybutton", "sphinx_design"]
source_suffix = {".md": "markdown"}
exclude_patterns = ["requirements.*"]

myst_enable_extensions = ["colon_fence", "deflist", "substitution"]
myst_heading_anchors = 3
myst_substitutions = {"repository": REPOSITORY}

html_theme = "furo"
html_title = "Local code generation"
html_baseurl = "https://niccokunzmann.github.io/satyrn-getting-started/"
html_theme_options = {
    "source_repository": REPOSITORY,
    "source_branch": "main",
    "source_directory": "docs/",
}

# Only the command is copied, not the comment after it.
copybutton_exclude = ".linenos, .gp, .c1"
