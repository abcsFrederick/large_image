#!/usr/bin/env python
# -*- coding: utf-8 -*-

#############################################################################
#  Copyright Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#############################################################################

import datetime
import json

from girder import events, plugin, logger
from girder.constants import AccessType, SettingDefault
from girder.exceptions import ValidationException
from girder.models.file import File
from girder.models.item import Item
from girder.models.notification import Notification
from girder.models.setting import Setting
from girder.utility import setting_utilities

from . import constants
from .models.annotation import Annotation
from .models.overlay import Overlay
from .models.image_item import ImageItem
from .loadmodelcache import invalidateLoadModelCache
from . import cache_util


def _postUpload(event):
    """
    Called when a file is uploaded. We check the parent item to see if it is
    expecting a large image upload, and if so we register this file as the
    result image.
    """
    fileObj = event.info['file']
    # There may not be an itemId (on thumbnails, for instance)
    if not fileObj.get('itemId'):
        return

    item = Item().load(fileObj['itemId'], force=True, exc=True)

    if item.get('largeImage', {}).get('expected') and (
            fileObj['name'].endswith('.tiff') or
            fileObj.get('mimeType') == 'image/tiff'):
        if fileObj.get('mimeType') != 'image/tiff':
            fileObj['mimeType'] = 'image/tiff'
            File().save(fileObj)
        del item['largeImage']['expected']
        item['largeImage']['fileId'] = fileObj['_id']
        item['largeImage']['sourceName'] = 'tiff'
        Item().save(item)

    if item.get('histogram', {}).get('expected') and (
            fileObj['name'].endswith('.json') or
            fileObj.get('mimeType') == 'application/json'):
        if fileObj.get('mimeType') != 'application/json':
            fileObj['mimeType'] = 'application/json'
            File().save(fileObj)
        del item['histogram']['expected']
        item['histogram']['fileId'] = fileObj['_id']
        Item().save(item)


def _updateJob(event):
    """
    Called when a job is saved, updated, or removed.  If this is a large image
    job and it is ended, clean up after it.
    """
    from girder.plugins.jobs.constants import JobStatus
    from girder.plugins.jobs.models.job import Job

    tasks = {
        'createImageItem':
            ('largeImage', 'Large image', 'finished_image_item'),
        'createHistogramItem':
            ('histogram', 'Histogram', 'finished_histogram_item'),
    }
    job = event.info['job'] if event.name == 'jobs.job.update.after' else event.info
    meta = job.get('meta', {})
    if (meta.get('creator') != 'large_image' or not meta.get('itemId') or
            meta.get('task') not in tasks):
        return
    field, description, notification = tasks[meta.get('task')]
    status = job['status']
    if event.name == 'model.job.remove' and status not in (
            JobStatus.ERROR, JobStatus.CANCELED, JobStatus.SUCCESS):
        status = JobStatus.CANCELED
    if status not in (JobStatus.ERROR, JobStatus.CANCELED, JobStatus.SUCCESS):
        return
    item = Item().load(meta['itemId'], force=True)
    if not item or field not in item:
        return
    if item.get(field, {}).get('expected'):
        # We can get a SUCCESS message before we get the upload message, so
        # don't clear the expected status on success.
        if status != JobStatus.SUCCESS:
            del item[field]['expected']
    notify = item.get(field, {}).get('notify')
    msg = None
    if notify:
        del item[field]['notify']
        if status == JobStatus.SUCCESS:
            msg = '%s created'
        elif status == JobStatus.CANCELED:
            msg = '%s creation canceled'
        else:  # ERROR
            msg = 'FAILED: %s creation failed'
        msg += ' for item %s'
        msg %= description, item['name']
    if (status in (JobStatus.ERROR, JobStatus.CANCELED) and
            field in item):
        del item[field]
    Item().save(item)
    if msg and event.name != 'model.job.remove':
        Job().updateJob(job, progressMessage=msg)
    if notify:
        Notification().createNotification(
            type='.'.join(('large_image', notification)),
            data={
                'job_id': job['_id'],
                'item_id': item['_id'],
                'success': status == JobStatus.SUCCESS,
                'status': status
            },
            user={'_id': job.get('userId')},
            expires=datetime.datetime.utcnow() + datetime.timedelta(seconds=30))


def checkForLargeImageFiles(event):
    file = event.info
    possible = False
    mimeType = file.get('mimeType')
    if mimeType in ('image/tiff', 'image/x-tiff', 'image/x-ptif'):
        possible = True
    exts = file.get('exts')
    if exts and exts[-1] in ('svs', 'ptif', 'tif', 'tiff', 'ndpi', 'mrxs'):
        possible = True
    if not file.get('itemId') or not possible:
        return
    if not Setting().get(constants.PluginSettings.LARGE_IMAGE_AUTO_SET):
        return
    item = Item().load(file['itemId'], force=True, exc=False)
    if not item or item.get('largeImage'):
        return
    try:
        ImageItem().createImageItem(item, file, createJob=False)
    except Exception:
        # We couldn't automatically set this as a large image
        logger.info('Saved file %s cannot be automatically used as a '
                    'largeImage' % str(file['_id']))


def removeThumbnails(event):
    ImageItem().removeThumbnailFiles(event.info)


def prepareCopyItem(event):
    """
    When copying an item, adjust the fileId reference so it can be
    matched to the to-be-copied file.
    """
    fields = ('largeImage', 'histogram')
    srcItem, newItem = event.info
    hasFields = [field for field in fields if field in newItem]
    for field in hasFields:
        li = newItem[field]
        for pos, file in enumerate(Item().childFiles(item=srcItem)):
            for key in ('fileId', 'originalId'):
                if li.get(key) == file['_id']:
                    li['_index_' + key] = pos
    if hasFields:
        Item().save(newItem, triggerEvents=False)


def handleCopyItem(event):
    """
    When copying an item, finish adjusting the fileId reference to
    the copied file.
    """
    fields = ('largeImage', 'histogram')
    newItem = event.info
    hasFields = [field for field in fields if field in newItem]
    for field in hasFields:
        li = newItem[field]
        files = list(Item().childFiles(item=newItem))
        for key in ('fileId', 'originalId'):
            pos = li.pop('_index_' + key, None)
            if pos is not None and 0 <= pos < len(files):
                li[key] = files[pos]['_id']
    if hasFields:
        Item().save(newItem, triggerEvents=False)


# Validators

@setting_utilities.validator({
    constants.PluginSettings.LARGE_IMAGE_SHOW_THUMBNAILS,
    constants.PluginSettings.LARGE_IMAGE_SHOW_VIEWER,
    constants.PluginSettings.LARGE_IMAGE_AUTO_SET,
    constants.PluginSettings.LARGE_IMAGE_ANNOTATION_HISTORY,
})
def validateBoolean(doc):
    val = doc['value']
    if str(val).lower() not in ('false', 'true', ''):
        raise ValidationException('%s must be a boolean.' % doc['key'], 'value')
    doc['value'] = (str(val).lower() != 'false')


@setting_utilities.validator({
    constants.PluginSettings.LARGE_IMAGE_SHOW_EXTRA,
    constants.PluginSettings.LARGE_IMAGE_SHOW_EXTRA_ADMIN,
})
def validateDictOrJSON(doc):
    val = doc['value']
    try:
        if isinstance(val, dict):
            doc['value'] = json.dumps(val)
        elif val is None or val.strip() == '':
            doc['value'] = ''
        else:
            parsed = json.loads(val)
            if not isinstance(parsed, dict):
                raise ValidationException('%s must be a JSON object.' % doc['key'], 'value')
            doc['value'] = val.strip()
    except (ValueError, AttributeError):
        raise ValidationException('%s must be a JSON object.' % doc['key'], 'value')


@setting_utilities.validator({
    constants.PluginSettings.LARGE_IMAGE_MAX_THUMBNAIL_FILES,
    constants.PluginSettings.LARGE_IMAGE_MAX_SMALL_IMAGE_SIZE,
})
def validateNonnegativeInteger(doc):
    val = doc['value']
    try:
        val = int(val)
        if val < 0:
            raise ValueError
    except ValueError:
        raise ValidationException('%s must be a non-negative integer.' % (
            doc['key'], ), 'value')
    doc['value'] = val


@setting_utilities.validator({
    constants.PluginSettings.LARGE_IMAGE_DEFAULT_VIEWER
})
def validateDefaultViewer(doc):
    doc['value'] = str(doc['value']).strip()


# Defaults

# Defaults that have fixed values can just be added to the system defaults
# dictionary.
SettingDefault.defaults.update({
    constants.PluginSettings.LARGE_IMAGE_SHOW_THUMBNAILS: True,
    constants.PluginSettings.LARGE_IMAGE_SHOW_VIEWER: True,
    constants.PluginSettings.LARGE_IMAGE_AUTO_SET: True,
    constants.PluginSettings.LARGE_IMAGE_MAX_THUMBNAIL_FILES: 10,
    constants.PluginSettings.LARGE_IMAGE_MAX_SMALL_IMAGE_SIZE: 4096,
    constants.PluginSettings.LARGE_IMAGE_ANNOTATION_HISTORY: True,
})


# Configuration and load

@plugin.config(
    name='Large image',
    description='Create, serve, and display large multiresolution images.',
    version='0.2.0',
    dependencies={'worker'},
)
def load(info):
    from .rest import TilesItemResource, LargeImageResource, \
                      AnnotationResource, OverlayResource

    TilesItemResource(info['apiRoot'])
    info['apiRoot'].large_image = LargeImageResource()
    info['apiRoot'].annotation = AnnotationResource()
    info['apiRoot'].overlay = OverlayResource()

    Item().exposeFields(level=AccessType.READ, fields='largeImage')
    Item().exposeFields(level=AccessType.READ, fields='histogram')
    # Ask for some models to make sure their singletons are initialized.
    Annotation()
    Overlay()

    events.bind('data.process', 'large_image', _postUpload)
    events.bind('jobs.job.update.after', 'large_image', _updateJob)
    events.bind('model.job.save', 'large_image', _updateJob)
    events.bind('model.job.remove', 'large_image', _updateJob)
    events.bind('model.folder.save.after', 'large_image',
                invalidateLoadModelCache)
    events.bind('model.group.save.after', 'large_image',
                invalidateLoadModelCache)
    events.bind('model.item.remove', 'large_image', invalidateLoadModelCache)
    events.bind('model.item.copy.prepare', 'large_image', prepareCopyItem)
    events.bind('model.item.copy.after', 'large_image', handleCopyItem)
    events.bind('model.item.save.after', 'large_image',
                invalidateLoadModelCache)
    events.bind('model.file.save.after', 'large_image',
                checkForLargeImageFiles)
    events.bind('model.item.remove', 'large_image', removeThumbnails)
    events.bind('server_fuse.unmount', 'large_image', cache_util.cachesClear)
