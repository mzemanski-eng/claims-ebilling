#!/bin/sh
cd /Users/michaelzemanski/claims-ebilling/frontend
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:$PATH"
exec node node_modules/.bin/next dev
