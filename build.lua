-- l3build configuration for semtex
-- Run: l3build check   -- regression tests
--      l3build doc     -- build documentation
--      l3build ctan    -- package for CTAN submission

module = "semtex"

-- Source files
sourcefiles = {"semtex.sty"}

-- Test directory
testfiledir = "testfiles"

-- Primary engine: pdftex
checkengines = {"pdftex"}

-- Check options: run tests quietly
checkopts = "-interaction=nonstopmode"

-- Documentation sources (none yet — will be semtex.dtx when converted)
-- docfiles = {"semtex.dtx"}

-- Files to install
installfiles = {"semtex.sty"}

-- CTAN metadata
ctanpkg = "semtex"
