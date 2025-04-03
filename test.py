import os, sys # multiple imports on one line (E401)

def test( ):
    print( "Hello, Linter!" )  # spacing issues, unnecessary spaces (E211, E201, E202)
    x = 42 
    y=  7
    if x>y:print("x is greater")  # no space after keyword, multiple statements (E701)
    return    x+y  # extra spaces before value

test(  )
