from distutils.core import setup

setup(
    name='giant-dipper',
    version='0.1',
    packages=['robin-stocks', 'PyYAML', 'pyotp'],
    url='https://github.com/wheaney/giant-dipper',
    license='GPL-3.0-only',
    author='Wayne Heaney',
    author_email='wayne.heaney@gmail.com',
    description='Trading algorithm that thrives on assets that make big, volatile movements in the short-term, yet '
                'demonstrate little-to-no movement in the long-term.'
)
