def say_hello(name:str):
    print(  f"Hello, {name}!" )

def add(a:int,b:int)->int:
    return a + b

def main():
    say_hello("World")
    result=add(5,10)
    print( "Result is:", result )

main()
