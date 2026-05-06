# Find codependent.sty from the canonical location (../../codependent.sty)
# and vendored support files from testfiles/support/.
ensure_path('TEXINPUTS', '../../');
ensure_path('TEXINPUTS', '../support/');
