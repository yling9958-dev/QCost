#!/usr/bin/env bash
set -euo pipefail
DIAGNOSTICS_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DIAGNOSTICS_PROJECT="$DIAGNOSTICS_ROOT/07_latex"
DIAGNOSTICS_BUILD="$DIAGNOSTICS_ROOT/06_reports/paper_build"
mkdir -p "$DIAGNOSTICS_BUILD"
export TEXINPUTS="$DIAGNOSTICS_PROJECT//:"
export TFMFONTS="$DIAGNOSTICS_PROJECT/texmf/fonts/tfm//:"
export VFFONTS="$DIAGNOSTICS_PROJECT/texmf/fonts/vf//:"
export T1FONTS="$DIAGNOSTICS_PROJECT/texmf/fonts/type1//:"
export ENCFONTS="$DIAGNOSTICS_PROJECT/texmf/fonts/enc//:"
cd "$DIAGNOSTICS_PROJECT"
for DIAGNOSTICS_PASS in 1 2 3; do
 pdflatex -interaction=nonstopmode -halt-on-error -jobname=SecPaper_Yaqi-2-QMF-Selection \
  -output-directory="$DIAGNOSTICS_BUILD" IEEE-conference-template-062824.tex \
  > "$DIAGNOSTICS_ROOT/06_reports/compile_pass${DIAGNOSTICS_PASS}.log" 2>&1
done
printf '%s\n' "$DIAGNOSTICS_BUILD/SecPaper_Yaqi-2-QMF-Selection.pdf"
