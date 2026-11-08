#!/usr/bin/env bash
set -euo pipefail
REVISION_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
REVISION_PROJECT="$REVISION_ROOT/05_latex"
export TEXINPUTS="$REVISION_PROJECT//:"
export TFMFONTS="$REVISION_PROJECT/texmf/fonts/tfm//:"
export VFFONTS="$REVISION_PROJECT/texmf/fonts/vf//:"
export T1FONTS="$REVISION_PROJECT/texmf/fonts/type1//:"
export ENCFONTS="$REVISION_PROJECT/texmf/fonts/enc//:"
cd "$REVISION_PROJECT"
for REVISION_PASS in 1 2 3; do
  pdflatex -interaction=nonstopmode -halt-on-error -jobname=SecPaper_Yaqi-2-NoBestFirst \
    -output-directory="$REVISION_ROOT/06_pdf" IEEE-conference-template-062824.tex \
    > "$REVISION_ROOT/07_reports/compile_pass${REVISION_PASS}.log" 2>&1
done
printf '%s\n' "$REVISION_ROOT/06_pdf/SecPaper_Yaqi-2-NoBestFirst.pdf"
