# cython: language_level=3
from distutils.core import setup
from Cython.Build import cythonize
def main():
    setup(
      name = 'Hello world app',
      ext_modules=cythonize([
            "luckbot/*.pyx",
      ], language="c++", language_level=3, nthreads=2),

    )

if __name__ == "__main__":
    main()
