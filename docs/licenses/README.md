# Runtime license fallbacks

Some Python runtime distributions omit Tcl/Tk license files. The build script prefers installed runtime notices and otherwise uses these official Tcl/Tk 8.6 license texts:

- Tcl: https://github.com/tcltk/tcl/blob/core-8-6-branch/license.terms
- Tk: https://github.com/tcltk/tk/blob/core-8-6-branch/license.terms

Retrieved 2026-10-12. Other dependency notices are collected from the installed distributions during release packaging.
