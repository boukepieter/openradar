#!/usr/bin/python
# -*- coding: utf-8 -*-
# (c) Nelen & Schuurmans.  GPL licensed, see LICENSE.rst.

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import division

import calendar
import datetime
import h5py
import logging
import numpy as np
import os

from pydap import client
from pydap.exceptions import ServerError

from openradar import calc
from openradar import config
from openradar import utils
from openradar import scans
from openradar.interpolation import DataLoader, Interpolator


class ThreddsFile(object):
    """
    Contains a number of products in h5 format.

    TODO Currently used to both write the files and retrieve the files from
    thredds, common functionality must be abstracted later.
    """
    REALTIME = 2
    NEARREALTIME = 3
    AFTERWARDS = 4
    FLAGS = dict(r=REALTIME, n=NEARREALTIME, a=AFTERWARDS)

    def __init__(self, datetime=None,
                 timeframe=None, prodcode='r', merge=True):
        """
        Return a threddsfile object configured with an url attribute
        that is suitable for use with opendap.
        """
        if datetime is None or timeframe is None:
            # Create a bare thredds_file object,
            # so get_for_product() does not break.
            return

        self.timeframe = timeframe
        self.datetime = self._datetime(datetime)
        self.timedelta = config.TIMEFRAME_DELTA[timeframe]
        self.timesteps = self._timesteps()
        self.prodcode = prodcode
        self.merge = merge

        basecode = config.PRODUCT_CODE[timeframe][prodcode]
        if merge:
            code = basecode.split('_')[0]
        else:
            code = basecode
        self.url = utils.PathHelper(
            basedir=config.OPENDAP_ROOT,
            code=code,
            template=config.PRODUCT_TEMPLATE,
        ).path(self.datetime)

    def _datetime(self, datetime):
        """ Return the timestamp of the threddsfile. """
        if self.timeframe == 'f':
            return datetime.replace(day=1, hour=0,
                                    minute=0, second=0, microsecond=0)
        if self.timeframe == 'h':
            return datetime.replace(month=1, day=1, hour=0,
                                    minute=0, second=0, microsecond=0)
        if self.timeframe == 'd':
            year = datetime.year // 20 * 20
            return datetime.replace(year=year, month=1, day=1, hour=0,
                                    minute=0, second=0, microsecond=0)

    def _timesteps(self):
        """ Return the amount of timesteps in this ThreddsFile """
        # Make a list of year, date tuples for use in monthrange.
        years = dict(f=1, h=1, d=20)[self.timeframe]
        months = dict(f=1, h=12, d=12)[self.timeframe]
        yearmonths = []
        for year in range(self.datetime.year,
                          self.datetime.year + years):
            for month in range(self.datetime.month,
                               self.datetime.month + months):
                yearmonths.append(dict(year=year, month=month))

        # Calculate total amount of days in the file:
        days = 0
        for yearmonth in yearmonths:
            days += calendar.monthrange(**yearmonth)[1]

        return days * dict(f=288, h=24, d=1)[self.timeframe]

    def _index(self, product):
        """
        Return the index for the time dimension for a product.

        Rounding is because of uncertainties in the total_seconds() method.
        """
        return round((product.datetime -
                      self.datetime).total_seconds() /
                     self.timedelta.total_seconds())

    def index(self, datetime):
        """
        Return the index for the time dimension for a datetime.

        Clips to first and last element.
        """
        unclipped = int((datetime - self.datetime).total_seconds() /
                        self.timedelta.total_seconds())
        return min(max(unclipped, 0), self.timesteps - 1)

    def _get_datetime_generator(self, start, end):
        """
        Return generator of datetimes for data at x, y.

        Start, end are indexes.
        """
        for i in range(start, end + 1):
            yield self.datetime + i * self.timedelta

    def get_data_from_opendap(self, x, y, start=None, end=None):
        """
        Return list of dicts for data at x, y.

        Start, end are datetimes, and default to the first and last
        datetime in the file.
        """
        try:
            dataset = client.open_url(self.url)
        except ServerError:
            return []

        index_start = 0
        if start is not None:
            index_start = self.index(start)

        if end is None:
            index_end = self.timesteps - 1
        else:
            index_end = self.index(end)

        precipitation = dataset['precipitation']['precipitation']

        tuples = zip(
            iter(self._get_datetime_generator(start=index_start,
                                              end=index_end)),
            precipitation[y, x, index_start: index_end + 1][0, 0, :],
        )

        return [dict(unit='mm/5min', datetime=d, value=float(p))
                for d, p in tuples
                if not p == config.NODATAVALUE]

    def next(self):
        """ Return thredds_file object that comes after this one in time. """
        last = list(self._get_datetime_generator(
            self.timesteps - 1, self.timesteps - 1)
        )[0]
        first_of_next = last + self.timedelta
        return ThreddsFile(datetime=first_of_next,
                           timeframe=self.timeframe,
                           prodcode=self.prodcode,
                           merge=self.merge)

    def _time(self):
        """ Return the fill for the time dataset. """
        step = round(self.timedelta.total_seconds())
        end = round(self.timesteps * step)
        return np.ogrid[0:end:step]

    @classmethod
    def get_for_product(cls, product, merge=False):
        """
        Return ThreddsFile instance to which product belongs.

        If merge == True, threddsfiles from all products are merged in
        one threddsfile per timeframe. The avalailable variable will
        contain a flag that refers to the product that was stored at a
        particular time coordinate. The paths will be the same regardless
        of the productcode, and the data will only be overwritten if
        the new flag is equal or higher than the already existing flag.
        The flags are:
            2: Realtime
            3: Near-realtime
            4: Afterwards
        """
        thredds_file = cls()
        thredds_file.timeframe = product.timeframe
        thredds_file.datetime = thredds_file._datetime(product.datetime)
        thredds_file.timedelta = config.TIMEFRAME_DELTA[product.timeframe]
        thredds_file.timesteps = thredds_file._timesteps()

        basecode = config.PRODUCT_CODE[product.timeframe][product.prodcode]
        if merge:
            code = basecode.split('_')[0]
            thredds_file.flag = cls.FLAGS[product.prodcode]
        else:
            code = basecode
            thredds_file.flag = 1

        thredds_file.path = utils.PathHelper(
            basedir=config.THREDDS_DIR,
            code=code,
            template=config.PRODUCT_TEMPLATE,
        ).path(thredds_file.datetime)
        return thredds_file

    def create(self):
        """ Return newly created threddsfile. """
        utils.makedir(os.path.dirname(self.path))
        h5 = h5py.File(self.path)

        # East
        east = scans.BASEGRID.get_grid()[0][0]
        dataset = h5.create_dataset(
            'east', east.shape, east.dtype,
            compression='gzip', shuffle=True,
        )
        dataset[...] = east

        # North
        north = scans.BASEGRID.get_grid()[1][:, 0]
        dataset = h5.create_dataset(
            'north', north.shape, north.dtype,
            compression='gzip', shuffle=True,
        )
        dataset[...] = north

        # Time
        time = h5.create_dataset(
            'time', [self.timesteps], np.uint32,
            compression='gzip', shuffle=True,
        )
        time.attrs['standard_name'] = b'time'
        time.attrs['long_name'] = b'time'
        time.attrs['calendar'] = b'gregorian'
        time.attrs['units'] = self.datetime.strftime(
            'seconds since %Y-%m-%d'
        )
        time[...] = self._time()

        # Precipitation
        shape = scans.BASEGRID.get_shape() + tuple([self.timesteps])
        dataset = h5.create_dataset(
            'precipitation', shape, np.float32, fillvalue=config.NODATAVALUE,
            compression='gzip', shuffle=True, chunks=(20, 20, 24)
        )

        # Availability
        dataset = h5.create_dataset(
            'available', [self.timesteps], np.uint8, fillvalue=0,
            compression='gzip', shuffle=True,
        )
        dataset[...] = 0

        # Dimensions
        h5['precipitation'].dims.create_scale(h5['north'])
        h5['precipitation'].dims.create_scale(h5['east'])
        h5['precipitation'].dims.create_scale(h5['time'])

        h5['precipitation'].dims[0].attach_scale(h5['north'])
        h5['precipitation'].dims[1].attach_scale(h5['east'])
        h5['precipitation'].dims[2].attach_scale(h5['time'])

        h5['available'].dims.create_scale(h5['time'])
        h5['available'].dims[0].attach_scale(h5['time'])

        logging.info(
            'Created ThreddsFile {}'.format(os.path.basename(self.path)),
        )
        logging.debug(self.path)
        return h5

    def check(self):
        """ Raise ValueError if check fails. """

        with h5py.File(self.path) as h5:
            if not 'time' in h5:
                raise ValueError("No 'time' dataset.")
            if not h5['time'].size == self.timesteps:
                raise ValueError('Expected size {}, found {}.'.format(
                    self.timesteps, h5['time'].size,
                ))

    def get_or_create(self):
        """
        Return h5 ready for writing.

        If already exists, it is checked against some criteria. If it
        fails the test or does not exist at all, a new file is created
        and initialized.
        """
        logging.debug(self.path)
        if not os.path.exists(self.path):
            return self.create()
        try:
            self.check()
        except ValueError as e:
            logging.debug('Check said: "{}"; Creating new file.'.format(e))
            os.remove(self.path)
            return self.create()
        return h5py.File(self.path)

    def update(self, product):
        """ Update from product """
        # Create or reuse existing thredds file
        h5_thredds = self.get_or_create()

        # Temporarily update
        try:
            del h5_thredds['time'].attrs['unit']
        except KeyError:
            pass  # It wasn't there anyway.
        h5_thredds['time'].attrs['units'] = self.datetime.strftime(
            'seconds since %Y-%m-%d'
        )

        # Update from products if necessary
        index = self._index(product)
        available = h5_thredds['available']
        if self.flag >= available[index]:
            target = h5_thredds['precipitation']
            with product.get() as h5_product:
                source = h5_product['precipitation']
                target[..., index] = source[...]
                available[index] = self.flag

        # Roundup
        logging.info('Updated {} ({})'.format(
            os.path.basename(self.path),
            product.datetime),
        )
        logging.debug(self.path)
        logging.debug('ThreddsFile fill status: {} %'.format(
            np.bool8(available[:]).sum() / available.size))

        h5_thredds.close()

    def get(self):
        """ Return readonly dataset. """
        return h5py.File(self.path, 'r')

    def __eq__(self, other):
        return unicode(self) == unicode(other)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        if hasattr(self, 'path'):
            return self.path
        if hasattr(self, 'url'):
            return self.url


class CalibratedProduct(object):
    '''
    Depending on the product requested the produce method will create:
    E.g. At 2012-12-18-09:05 the products that can be made at that moment
        depending on the product are:
            real-time           => 2012-12-18-09:05
            near-real-time      => 2012-12-18-08:05
            afterwards          => 2012-12-16-09:05
    '''

    def __init__(self, prodcode, timeframe,
                 datetime, radars=None, declutter=None):
        # Attributes
        self.datetime = datetime
        self.prodcode = prodcode
        self.timeframe = timeframe
        # Derived attributes
        self.radars = config.ALL_RADARS if radars is None else radars
        if declutter is None:
            self.declutter = dict(size=config.DECLUTTER_SIZE,
                                  history=config.DECLUTTER_HISTORY)
        else:
            self.declutter = declutter

        # Determine the groundpath and groundfile datetime
        self.grounddata = self._get_grounddata()
        self.groundpath = self.grounddata.get_datapath()
        self.groundfile_datetime = self.grounddata._datetime

        self.path = utils.PathHelper(
            basedir=config.CALIBRATE_DIR,
            code=config.PRODUCT_CODE[self.timeframe][self.prodcode],
            template=config.PRODUCT_TEMPLATE,
        ).path(datetime)

    def _get_grounddata(self):
        """ Return the best existing GroundData instance. """
        datacode = config.GROUND_CODE[self.timeframe]
        datetimes = utils.get_groundfile_datetimes(date=self.datetime,
                                                   prodcode=self.prodcode,
                                                   timeframe=self.timeframe)
        for datetime in datetimes:
            grounddata = scans.GroundData(datacode=datacode,
                                          datadatetime=datetime)
            root, ext = os.path.splitext(grounddata.get_datapath())
            for extension in ['.zip', '.csv']:
                path = root + extension
                if os.path.exists(path):
                    logging.debug('Groundfile selected: {}'.format(path))
                    return grounddata
        # Always return a grounddata object
        logging.warning('Groundfile not found, returning: {}'.format(path))
        return grounddata

    def _get_aggregate(self):
        """ Return Aggregate object. """
        return scans.Aggregate(radars=self.radars,
                               datetime=self.datetime,
                               timeframe=self.timeframe,
                               declutter=self.declutter)

    def make(self):
        aggregate = self._get_aggregate()
        aggregate.make()
        if self.groundfile_datetime.year < 2012:
            groundpath = os.path.join(config.MISC_DIR, 'tests/2011.csv')
        else:
            groundpath = self.groundpath
        metafile = os.path.join(config.MISC_DIR, 'grondstations.csv')
        dataloader = DataLoader(metafile=metafile,
                                datafile=groundpath,
                                aggregate=aggregate)
        try:
            dataloader.processdata()
            stations_count = len(dataloader.rainstations)
            data_count = len([r
                              for r in dataloader.rainstations
                              if r.measurement != -999])
            logging.info('{} out of {} gauges have data for {}.'.format(
                data_count, stations_count, dataloader.date)
            )
        except:
            logging.exception('Exception during calibration preprocessing:')
            stations_count = 0
        interpolator = Interpolator(dataloader)

        # Calibrate, method depending on prodcode and timeframe
        precipitation_mask = np.equal(
            interpolator.precipitation,
            config.NODATAVALUE,
        )
        if data_count == 0:
            logging.info('Calibrating is not useful without stations.')
            calibration_method = 'None'
            calibrated_radar = np.ma.array(
                interpolator.precipitation,
                mask=precipitation_mask,
            )
        elif self.prodcode == 'a' and self.timeframe in ['h', 'd']:
            logging.info('Calibrating using kriging.')
            calibration_method = 'Kriging External Drift'
            try:
                calibrated_radar = np.ma.where(
                    precipitation_mask,
                    interpolator.precipitation,
                    interpolator.get_calibrated(),
                )
            except:
                logging.exception('Exception during kriging:')
                calibrated_radar = None
        else:
            logging.info('Calibrating using idw.')
            calibration_method = 'Inverse Distance Weigting'
            try:
                factor = interpolator.get_correction_factor()
                calibrated_radar = np.ma.where(
                    precipitation_mask,
                    interpolator.precipitation,
                    interpolator.precipitation * factor,
                )
            except:
                logging.exception('Exception during idw:')
                calibrated_radar = None

        if calibrated_radar is None:
            logging.warn('Calibration failed.')
            calibration_method = 'None'
            self.calibrated = interpolator.precipitation
        else:
            mask = utils.get_countrymask()
            self.calibrated = (mask * calibrated_radar +
                               (1 - mask) * interpolator.precipitation)

        self.metadata = dict(dataloader.dataset.attrs)
        dataloader.dataset.close()
        # Append metadata about the calibration
        self.metadata.update(dict(
            cal_stations_count=stations_count,
            cal_data_count=data_count,
            cal_method=calibration_method,
        ))

        calibrated_ma = np.ma.array(
            self.calibrated,
            mask=np.equal(self.calibrated, config.NODATAVALUE),
        )

        logging.debug('Setting negative values to 0. Min was: {}'.format(
            calibrated_ma.min()),
        )
        calibrated_ma[np.ma.less(calibrated_ma, 0)] = 0

        utils.save_dataset(path=self.path,
                           meta=self.metadata,
                           data=dict(precipitation=calibrated_ma))

        logging.info('Created CalibratedProduct {}'.format(
            os.path.basename(self.path)
        ))
        logging.debug(self.path)

    def get(self):
        try:
            return h5py.File(self.path, 'r')
        except IOError:
            logging.warn(
                'Creating calibrated product {}, because it did not'
                ' exist'.format(self.path)),
            self.make()
        return h5py.File(self.path, 'r')

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return self.path


class ConsistentProduct(object):
    """ Conisitified products are usually created by the consisitier. """

    def __init__(self, datetime, prodcode, timeframe):
        self.datetime = datetime
        self.date = datetime  # Backwards compatible
        self.prodcode = prodcode
        self.product = prodcode  # Backwards compatible
        self.timeframe = timeframe
        self.path = utils.PathHelper(
            basedir=config.CONSISTENT_DIR,
            code=config.PRODUCT_CODE[self.timeframe][self.prodcode],
            template=config.PRODUCT_TEMPLATE,
        ).path(datetime)

    def get(self):
        """
        Return h5 dataset opened in read mode.

        Crashes when the file does not exist. This should be catched by caller.
        """
        return h5py.File(self.path, 'r')

    @classmethod
    def create(cls, product, factor, consistent_with):
        """
        Return ConsistentProduct.

        Creates a ConsistentProduct from product with data multiplied
        by factor and adds consistent_with to the metadata.
        """
        # Create the consistent product object
        consistent_product = cls(
            datetime=product.datetime,
            prodcode=product.prodcode,
            timeframe=product.timeframe,
        )

        # Create the h5 datafile for it
        with product.get() as h5:
            data = h5['precipitation']
            mask = np.equal(data, config.NODATAVALUE)
            data = dict(precipitation=np.ma.array(data, mask=mask) * factor)
            meta = dict(h5.attrs)
            meta.update(consistent_with=consistent_with)
        utils.save_dataset(
            data=data,
            meta=meta,
            path=consistent_product.path
        )

        # get() will now work, so return the object.
        filepath = consistent_product.path
        filename = os.path.basename(filepath)
        logging.info('Created ConsistentProduct {}'.format(filename))
        logging.debug('Created ConsistentProduct {}'.format(filepath))
        return consistent_product

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return self.path


class Consistifier(object):
    """
    The products that are updated afterwards with new gaugestations need to
    be consistent with the aggregates of the same date.
    E.g. In the hour 12.00 there are 12 * 5 minute products and 1 one hour
    product. The 12 seperate 5 minutes need add up to the same amount of
    precipitation as the hourly aggregate.

    The consistent products are only necessary for 3 products:
        - 5 minute near-realtime
        - 5 minute afterwards
        - hour near-realtime

    Is a class purily for encapsulation purposes.
    """
    SUB_TIMEFRAME = {'d': 'h', 'h': 'f'}

    @classmethod
    def _reliable(cls, product):
        """
        Return if product enables consistification of other products.
        """
        prodcode, timeframe = product.prodcode, product.timeframe
        if prodcode == 'a':
            if timeframe == 'd':
                return True
            if timeframe == 'h' and isinstance(product, ConsistentProduct):
                return True
        if prodcode == 'n' and timeframe == 'h':
            return True
        return False

    @classmethod
    def _subproduct_datetimes(cls, product):
        """ Return datetimes for subproducts of product. """
        amount_of_subproducts = dict(h=12, d=24)[product.timeframe]
        sub_timeframe = cls.SUB_TIMEFRAME[product.timeframe]
        sub_timedelta = config.TIMEFRAME_DELTA[sub_timeframe]
        for i in range(amount_of_subproducts):
            offset = sub_timedelta * (i - amount_of_subproducts + 1)
            yield product.datetime + offset

    @classmethod
    def _subproducts(cls, product):
        """ Return the CalibratedProducts to be consistified with product """
        sub_timeframe = cls.SUB_TIMEFRAME[product.timeframe]
        for datetime in cls._subproduct_datetimes(product):
            yield CalibratedProduct(datetime=datetime,
                                    prodcode=product.prodcode,
                                    timeframe=sub_timeframe)

    @classmethod
    def _precipitation_from_product(cls, product):
        """ Return precipitation as masked array. """
        with product.get() as h5:
            data = h5['precipitation']
            mask = np.equal(data, config.NODATAVALUE)
            precipitation = np.ma.array(data, mask=mask)
        return precipitation

    @classmethod
    def create_consistent_products(cls, product):
        """ Returns a list of consistent products that were created. """
        consistified_products = []
        if cls._reliable(product):
            # Calculate sum of subproducts
            subproduct_sum = np.ma.zeros(scans.BASEGRID.get_shape())
            for subproduct in cls._subproducts(product):
                    subproduct_sum = np.ma.sum([
                        subproduct_sum,
                        cls._precipitation_from_product(subproduct),
                    ], 0)

            # Calculate factor
            factor = np.where(
                np.ma.equal(subproduct_sum, 0),
                1,
                cls._precipitation_from_product(product) / subproduct_sum,
            )

            # Create consistent products
            for subproduct in cls._subproducts(product):
                consistified_products.append(
                    ConsistentProduct.create(
                        product=subproduct,
                        factor=factor,
                        consistent_with=os.path.basename(subproduct.path)
                    )
                )
            # Run this method on those products as well, since some
            # consistified products allow for consistent products themselves,
            # For example a.d consistifies a.h which in turn consitifies a.f.
            more_consistified_products = []
            for consistified_product in consistified_products:
                more_consistified_products.extend(
                    cls.create_consistent_products(consistified_product)
                )
            consistified_products.extend(more_consistified_products)
        return consistified_products

    @classmethod
    def get_rescaled_products(cls, product):
        """ Return the rescaled products that are scaled to product. """
        rescaled_products = []
        if cls._reliable(product):
            rescaled_products.extend(
                [ConsistentProduct(datetime=p.datetime,
                                   prodcode=p.prodcode,
                                   timeframe=p.timeframe)
                 for p in cls._subproducts(product)],
            )
        extra_rescaled_products = []
        for rescaled_product in rescaled_products:
            extra_rescaled_products.extend(
                cls.get_rescaled_products(rescaled_product),
            )
        rescaled_products.extend(extra_rescaled_products)
        return rescaled_products


def get_values_from_opendap(x, y, start_date, end_date):
    result = []
    current = ThreddsFile(timeframe='f', datetime=start_date)
    end = ThreddsFile(timeframe='f', datetime=end_date)
    while True:
        result.extend(current.get_data_from_opendap(x=x,
                                                    y=y,
                                                    start=start_date,
                                                    end=end_date))
        if current == end:
            return result
        current = current.next()


class NowcastProduct(object):
    """
    Represents a nowcasted product. All source products are included in
    the metadata.
    """
    def __init__(self, datetime, timeframe, **kwargs):
        self.datetime = datetime
        self.timeframe = timeframe
        self.prodcode = 'r'
        self.path = utils.PathHelper(
            basedir=config.NOWCAST_DIR,
            code=config.PRODUCT_CODE[self.timeframe][self.prodcode],
            template=config.PRODUCT_TEMPLATE,
        ).path(datetime)

    def get(self):
        """
        Return h5 dataset opened in read mode.

        Crashes when the file does not exist. This should be catched by caller.
        """
        return h5py.File(self.path, 'r')

    def make(self, base_product, vector_products, vector_extent=None):
        """
        :param baseproduct: the product whose preciptation to shift
        :param vectorproducts:
            two-tuple of products to derive the shift vector from
        :param vectorextent:
            extent to limit the data region from which the vector is derived
        """
        correlate_data = []
        for vector_product in vector_products:
            with vector_product.get() as h5:
                linear_correlate_data = np.ma.masked_equal(
                    h5['precipitation'],
                    config.NODATAVALUE,
                ).filled(0)
            correlate_data.append(np.log(linear_correlate_data + 1))
            #correlate_data.append(linear_correlate_data)

        # Determine the slices into the data. It is assumed that the data
        # have the same shape and that the extent of the data corresponds
        # to the configured composite extent.
        if vector_extent is None:
            #vector_extent = 58000, 431000, 116000, 471000
            vector_extent = 46126, 416638, 140226, 480951
            # mpl style extent to gdal style extent
            full_extent = np.array(
                config.COMPOSITE_EXTENT,
            )[[0, 3, 1, 2]].tolist()
        slices = calc.calculate_slices(
            size=correlate_data[0].shape[::-1],
            full_extent=full_extent,
            partial_extent=vector_extent,
        )

        # get the vector
        vector = calc.calculate_vector(*map(lambda x: x[slices],
                                       correlate_data))
        logging.debug(vector)
        vector_products_seconds = (vector_products[1].datetime -
                                   vector_products[0].datetime).total_seconds()
        base_product_seconds = (self.datetime -
                                base_product.datetime).total_seconds()
        factor = base_product_seconds / vector_products_seconds
        shift = [-v * factor for v in vector]

        # Load the base data
        with base_product.get() as h5:
            original = h5['precipitation'][:]
            meta = dict(h5.attrs)
        original_filled = np.ma.masked_equal(
            original, config.NODATAVALUE, copy=False,
        ).filled(0)

        # Create nowcast data by adding shifted data
        current_datetime = (self.datetime - 
                            config.TIMEFRAME_DELTA[self.timeframe])
        nowcast_precipitation = np.zeros(original.shape, 'f4')
        count = 0
        while current_datetime < self.datetime:
            current_datetime += datetime.timedelta(minutes=5)
            # De-indent this tot get only shift, but now accumulation
            seconds = (current_datetime -
                       base_product.datetime).total_seconds()
            factor = seconds / vector_products_seconds
            shift = [-v * factor for v in vector]
            nowcast_precipitation += calc.calculate_shifted(
                data=original_filled, 
                shift=shift,
            )
            count += 1
        logging.debug(count)

        # Wrap
        data = dict(
            precipitation=np.ma.masked_equal(
                nowcast_precipitation,
                config.NODATAVALUE,
            ),
        )

        # Utils save dataset checks timestamp_last_composite.
        # Add the difference between product and baseproduct.
        datetime_last_composite = utils.timestamp2datetime(
            meta['timestamp_last_composite'],
        ) + (self.datetime - base_product.datetime)
        timestamp_last_composite=datetime_last_composite.strftime(
            config.TIMESTAMP_FORMAT,
        )

        meta.update(
            timestamp_last_composite=timestamp_last_composite,
            nowcast_v0=os.path.basename(vector_products[0].path),
            nowcast_v1=os.path.basename(vector_products[1].path),
            nowcast_base=os.path.basename(base_product.path),
            nowcast_seconds=int(base_product_seconds),
        )

        # Save and log
        utils.save_dataset(
            data=data,
            meta=meta,
            path=self.path
        )
        filepath = self.path
        filename = os.path.basename(self.path)
        logging.info('Created NowcastProduct {}'.format(filename))
        logging.debug('v0 {}'.format(vector_products[0]))
        logging.debug('v1 {}'.format(vector_products[1]))
        logging.debug('base {}'.format(base_product))
        logging.debug('Created NowcastProduct {}'.format(filepath))

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return self.path
