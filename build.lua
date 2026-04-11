-- l3build configuration for codependent
-- Run: l3build check   -- regression tests
--      l3build doc     -- build documentation
--      l3build ctan    -- package for CTAN submission

module = "codependent"

-- Source files
sourcefiles = {"codependent.sty"}

-- Test directory
testfiledir = "testfiles"

-- Primary engine: pdftex
checkengines = {"pdftex"}

-- Check options: run tests quietly
checkopts = "-interaction=nonstopmode"

-- Documentation sources (none yet — will be codependent.dtx when converted)
-- docfiles = {"codependent.dtx"}

-- Files to install
installfiles = {"codependent.sty"}

-- CTAN metadata
ctanpkg = "codependent"
