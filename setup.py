from distutils.core import setup
from os import path


def generate_long_description_file():
    this_directory = path.abspath(path.dirname(__file__))
    with open(path.join(this_directory, 'README.md')) as f:
        long_description = f.read()
    return long_description


setup(
    name='giant_dipper',
    version='0.1.3',
    packages=['giant_dipper'],
    install_requires=['robin-stocks', 'PyYAML', 'pyotp'],
    url='https://github.com/wheaney/giant-dipper',
    license='GPL-3.0-only',
    author='Wayne Heaney',
    author_email='wayne.heaney@gmail.com',
    description='Trading algorithm that thrives on assets that make big, volatile movements in the short-term, yet '
                'demonstrate little-to-no movement in the long-term.',
    long_description=generate_long_description_file(),
    long_description_content_type='text/markdown'
)
