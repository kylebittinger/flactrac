from setuptools import setup

setup(
    name='flactrac',
    version='0.0.1',
    description='Convert FLAC and WAV files',
    author='Kyle Bittinger',
    author_email='kylebittinger@gmail.com',
    url='https://github.com/kylebittinger/flactrac',
    packages=['flactraclib'],
    entry_points = {
        'console_scripts': [
            'FlacTrac=flactraclib.command:main',
        ],
    }
)
