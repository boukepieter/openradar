Changelog of openradar
===================================================


0.2.9 (unreleased)
------------------

- Nothing changed yet.


0.2.8 (2013-02-13)
------------------

- Fix bug regarding missing shapedir.


0.2.7 (2013-02-13)
------------------

- Major rewrite of configuration system. Most configuration is now moved to this package. Stuff may be broken now, but it enables standalone testing of this library in the future.


0.2.6 (2013-02-12)
------------------

- Publish a merged threddsfile as well, where the realtime products
  are overwritten by near-realtime products, etc. The available variable
  functions as a flag to indicate what data was written.

- Range is now an optional positional argument.


0.2.5 (2013-01-25)
------------------

- Create the animated gif as tempfile, then move to actual target.


0.2.4 (2013-01-24)
------------------

- Add animated gif creation.


0.2.3 (2013-01-22)
------------------

- Add script for syncing of ftp folders (hirlam, eps)


0.2.2 (2013-01-21)
------------------

- Even less crashing of threddsfiles.


0.2.1 (2013-01-18)
------------------

- No logging for FtpImporter if nothing fetched.

- Fix crashing when creating new threddsfiles.


0.2.0 (2013-01-17)
------------------

- Format logging and show ftp result summary in logfile.

- No longer prepare google gtiff for web viewer.

- Delete existing h5 when creating, even if opening in 'w' mode.


0.1.9 (2013-01-17)
------------------

- Add ftp info to config

- Add FtpImporter that imports directly from scanfile sources.


0.1.8 (2013-01-17)
------------------

- CSV is now read from zipfile if it exists.

- Organize now moves anything with a csv extension to a zipped csv.


0.1.7 (2013-01-16)
------------------

- Separate error handling for creation and publishing.

- Update existing threddsfiles when publishing.

- Moving to much larger threddsfiles of around 10000 grids.


0.1.6 (2013-01-10)
------------------

- Re-enable multiprocessing.

- Fix n, h products not being published.

- Do local copying to subfolders per product.


0.1.5 (2013-01-10)
------------------

- Improved publishing routine. Will publish in order of importance.

- Created FtpPublisher that takes care of using folders on ftp.

- Tweaks to log messages.


0.1.4 (2013-01-09)
------------------

- Fix bug that tried to make d product at 9


0.1.3 (2013-01-09)
------------------

- Fix bug in get method of ConsistentProduct.


0.1.2 (2013-01-09)
------------------

- Set threshold for rain to 0.008 (that is 0.1 / 12)


0.1.1 (2013-01-09)
------------------

- Add master script.


0.1 (2013-01-09)
----------------

- Initial project structure created with nensskel 1.30.dev0.

- Add code from nens/radar project.
