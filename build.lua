-- l3build configuration for codependent
-- Run: l3build check          -- regression tests
--      l3build save <name>    -- generate/update .tlg for a test
--      l3build doc            -- build documentation
--      l3build ctan           -- package for CTAN submission

module = "codependent"

-- Source files
sourcefiles = {"codependent.sty"}

-- Test directory: l3build expects a flat dir with .lvt + .tlg files.
-- Our tests live in testfiles/unit/ and testfiles/integration/ for the
-- custom runner (scripts/run-tests.py).  Symlinks in testfiles/ point to those
-- subdirectories so l3build can discover them.
testfiledir = "testfiles"

-- Primary engine: pdftex (we only test pdflatex)
checkengines = {"pdftex"}

-- Load regression-test.tex automatically before each .lvt file.
-- Standard l3build practice is `\input regression-test` in every .lvt,
-- but the custom runner (scripts/run-tests.py) injects its own \START/\END
-- no-ops and would break if regression-test.tex redefines \END to
-- call \@@end.  Using tokens= lets l3build prepend the load while
-- keeping the .lvt files runner-agnostic.
specialformats = specialformats or {}
specialformats.latex = specialformats.latex or {}
specialformats.latex.pdftex = {
  tokens = "\\input regression-test\\relax "
}

-- Multiple compilation runs for cross-reference convergence.
-- Most tests need 2-3 runs for aux/sbl stabilisation.
checkruns = 3

-- Check options: nonstop mode
checkopts = "-interaction=nonstopmode"

-- Exclude the lualatex-specific test (it tests engine compat, not package logic;
-- running it under pdftex defeats its purpose).
excludetests = {"test-engine-lualatex"}

-- Documentation sources (none yet -- will be codependent.dtx when converted)
-- docfiles = {"codependent.dtx"}

-- Files to install
installfiles = {"codependent.sty"}

-- CTAN metadata
ctanpkg = "codependent"
