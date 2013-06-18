from setuptools import setup

version = '0.3.5.dev0'

long_description = '\n\n'.join([
    open('README.rst').read(),
    open('CREDITS.rst').read(),
    open('CHANGES.rst').read(),
    ])

install_requires = [
    'celery',
    'h5py',
    'matplotlib',
    'numpy',
    'Pillow',
    'pydap >= 3.1.RC1',
    'pytz',
    'rpy2',
    'scipy',
    'setuptools',
    'SQLAlchemy',
    'supervisor',
    ],

tests_require = [
    ]

setup(name='openradar',
      version=version,
      description="TODO",
      long_description=long_description,
      # Get strings from http://www.python.org/pypi?%3Aaction=list_classifiers
      classifiers=[],
      keywords=[],
      author='TODO',
      author_email='TODO@nelen-schuurmans.nl',
      url='',
      license='GPL',
      packages=['openradar'],
      include_package_data=True,
      zip_safe=False,
      install_requires=install_requires,
      tests_require=tests_require,
      extras_require={'test': tests_require},
      entry_points={
          'console_scripts': [
              # Main tasks
              'master = openradar.scripts.master:main',
              'sync = openradar.scripts.sync:main',
              'cleanup = openradar.scripts.cleanup:main',
              # Subtasks
              'aggregate = openradar.scripts.aggregate:main',
              'calibrate = openradar.scripts.calibrate:main',
              'rescale = openradar.scripts.rescale:main',
              'publish = openradar.scripts.publish:main',
              # Tools
              'sandbox = openradar.scripts.sandbox:main',
              'organize = openradar.scripts.organize:main',
              'image = openradar.scripts.image:main',
              
          ]},
      )
