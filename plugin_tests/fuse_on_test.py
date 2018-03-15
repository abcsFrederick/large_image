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

import os
import tempfile
import time

from girder import config
from girder.models.file import File
from girder.models.item import Item
from tests import base

from . import common


# boiler plate to start and stop the server

os.environ['GIRDER_PORT'] = os.environ.get('GIRDER_TEST_PORT', '20200')
config.loadConfig()  # Must reload config to pickup correct port


def setUpModule():
    curConfig = config.getConfig()
    curConfig.setdefault('server_fuse', {})
    curConfig['server_fuse']['path'] = tempfile.mkdtemp()
    base.enabledPlugins.append('large_image')
    base.enabledPlugins.append('fuse')
    base.startServer()


def tearDownModule():
    from girder.plugins.fuse import server_fuse

    from girder.plugins.large_image import cache_util
    import gc

    cache_util.cachesClear()
    gc.collect()

    server_fuse.unmountAll()
    curConfig = config.getConfig()
    tempdir = curConfig.get('server_fuse', {}).get('path')
    base.stopServer()
    retries = 0
    while retries < 50 and tempdir:
        try:
            os.rmdir(tempdir)
            break
        except OSError:
            retries += 1
            time.sleep(0.1)


class LargeImageWithFuseGridFSTest(common.LargeImageCommonTest):
    def setUp(self):
        super(LargeImageWithFuseGridFSTest, self).setUp(assetstoreType='gridfs')

    def testGridFSAssetstore(self):
        from girder.plugins.large_image.models.image_item import ImageItem

        file = self._uploadFile(os.path.join(
            os.environ['LARGE_IMAGE_DATA'], 'sample_image.ptif'))
        itemId = str(file['itemId'])
        item = Item().load(itemId, user=self.admin)
        # We should be able to read the metadata
        source = ImageItem().tileSource(item)
        metadata = source.getMetadata()
        self.assertEqual(metadata['sizeX'], 58368)
        self.assertEqual(metadata['sizeY'], 12288)
        self.assertEqual(metadata['levels'], 9)


class LargeImageWithFuseFSTest(common.LargeImageCommonTest):
    def testFilesystemAssetstore(self):
        from girder.plugins.large_image.models.image_item import ImageItem
        from girder.plugins.large_image.tilesource.tiff import TiffGirderTileSource

        TiffGirderTileSource.mayHaveAdjacentFiles = True

        file = self._uploadFile(os.path.join(
            os.environ['LARGE_IMAGE_DATA'], 'sample_image.ptif'))
        itemId = str(file['itemId'])
        item = Item().load(itemId, user=self.admin)
        file = File().load(item['largeImage']['fileId'], force=True)
        source = ImageItem().tileSource(item)
        # The file path should not be the local path, since we told it we might
        # have adjacent files.
        self.assertNotEqual(source._getLargeImagePath(), File().getLocalFilePath(file))
