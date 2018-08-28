import json

from bson.objectid import ObjectId

from girder.api import access
from girder.api.describe import autoDescribeRoute, Description
from girder.api.rest import Resource, filtermodel
from girder.constants import AccessType, TokenScope
from girder.exceptions import RestException
from girder.models.model_base import ValidationException
from girder.models.item import Item
from girder.models.file import File
from ..models.colormap import Colormap

class ColormapResource(Resource):
    def __init__(self):
        super(ColormapResource, self).__init__()

        self.resourceName = 'colormap'
        self.route('GET', (), self.find)
        self.route('POST', (), self.createColormap)
        self.route('POST', ('file', ':fileId'), self.createColormapFromFile)
        self.route('DELETE', (':id',), self.deleteColormap)
        self.route('GET', (':id',), self.getColormap)
        self.route('PUT', (':id',), self.updateColormap)
        self.route('GET', (':id', 'access'), self.getColormapAccess)
        self.route('PUT', (':id', 'access'), self.updateColormapAccess)

    @access.public(scope=TokenScope.DATA_READ)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Search for colormaps.')
        .responseClass('Colormap', array=True)
        .param('name', 'The name of the colormap.', required=False)
        .param('creatorId', 'The creator ID of the colormap.', required=False)
        .pagingParams(defaultSort='name')
        .errorResponse()
        .errorResponse('No matching colormaps were found.', 404)
    )
    def find(self, name, creatorId, limit, offset, sort):
        user = self.getCurrentUser()
        query = {}
        if name is not None:
            query['name'] = name
        if creatorId is not None:
            query['creatorId'] = ObjectId(creatorId)
        return list(Colormap().filterResultsByPermission(
            cursor=Colormap().find(query, sort=sort),
            user=user,
            level=AccessType.READ,
            limit=limit, offset=offset
        ))

    @access.user(scope=TokenScope.DATA_WRITE)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Create a colormap.')
        .responseClass('Colormap')
        .param('name', 'Name for the colormap.', required=False, strip=True)
        .param('public', 'Whether the colormap should be publicly visible.',
               dataType='boolean', required=False, default=False)
        .jsonParam('colormap', 'A JSON-encoded colormap.', requireObject=True)
        .errorResponse('Write access was denied for the colormap.', 403)
    )
    def createColormap(self, name, public, colormap):
        try:
            return Colormap().createColormap(
                self.getCurrentUser(), colormap, name, public)
        except ValidationException as exc:
            logger.exception('Failed to validate colormap')
            raise RestException(
                'Validation Error: JSON doesn\'t follow schema (%r).' % (
                    exc.args, ))

    @access.user(scope=TokenScope.DATA_WRITE)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Create a colormap from a file.')
        .responseClass('Colormap')
        .param('name', 'Name for the colormap.', required=False, strip=True)
        .param('public', 'Whether the colormap should be publicly visible.',
               dataType='boolean', required=False)
        .modelParam('fileId', model='file', level=AccessType.READ)
        .errorResponse('Write access was denied for the colormap.', 403)
    )
    def createColormapFromFile(self, name, public, file):
        params = json.load(File().open(file))
        colormap = params.get('colormap', {})
        if name is None:
            name = params.get('name')
        if public is None:
            public = params.get('public', False)
        try:
            return Colormap().createColormap(
                self.getCurrentUser(), colormap, name, public)
        except ValidationException as exc:
            logger.exception('Failed to validate colormap')
            raise RestException(
                'Validation Error: JSON doesn\'t follow schema (%r).' % (
                    exc.args, ))

    @access.user(scope=TokenScope.DATA_OWN)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Delete a colormap.')
        .modelParam('id', model='colormap', plugin='large_image',
                    level=AccessType.WRITE)
        .errorResponse('ID was invalid.')
        .errorResponse('Write access was denied for the colormap.', 403)
    )
    def deleteColormap(self, colormap):
        Colormap().remove(colormap)

    @access.public(scope=TokenScope.DATA_READ)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Get colormap by ID.')
        .responseClass('Colormap')
        .modelParam('id', model='colormap', plugin='large_image',
                    level=AccessType.READ)
        .errorResponse('ID was invalid.')
        .errorResponse('Read access was denied for the colormap.', 403)
    )
    def getColormap(self, colormap):
        return colormap

    @access.user(scope=TokenScope.DATA_WRITE)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Update a colormap.')
        .responseClass('Colormap')
        .modelParam('id', model='colormap', plugin='large_image',
                    destName='model', level=AccessType.WRITE)
        .param('name', 'Name for the colormap.', required=False)
        .jsonParam('colormap', 'A JSON-encoded colormap.', required=False,
                   requireObject=True)
        .errorResponse('Write access was denied for the colormap.', 403)
        .errorResponse('Color map not found.', 404)
    )
    def updateColormap(self, model, name, colormap):
        user = self.getCurrentUser()
        if name is not None:
            model['name'] = name
        if colormap is not None:
            model['colormap'] = colormap
        try:
            return Colormap().updateColormap(model, updateUser=user)
        except ValidationException as exc:
            logger.exception('Failed to validate colormap')
            raise RestException(
                'Validation Error: JSON doesn\'t follow schema (%r).' % (
                    exc.args, ))

    @access.user(scope=TokenScope.DATA_OWN)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Get the access control list for a colormap.')
        .modelParam('id', model='colormap', plugin='large_image',
                    level=AccessType.ADMIN)
        .errorResponse('ID was invalid.')
        .errorResponse('Admin access was denied for the colormap.', 403)
    )
    def getColormapAccess(self, colormap):
        return Colormap().getFullAccessList(colormap)

    @access.user(scope=TokenScope.DATA_OWN)
    @filtermodel(model='colormap', plugin='large_image')
    @autoDescribeRoute(
        Description('Update the access control list for a colormap.')
        .responseClass('Colormap')
        .modelParam('id', model='colormap', plugin='large_image',
                    level=AccessType.ADMIN)
        .jsonParam('access', 'The JSON-encoded access control list.')
        .param('public', 'Whether the colormap should be publicly visible.',
               dataType='boolean', required=False)
        .errorResponse('ID was invalid.')
        .errorResponse('Admin access was denied for the colormap.', 403)
    )
    def updateColormapAccess(self, colormap, access, public):
        Colormap().setPublic(colormap, public)
        return Colormap().setAccessList(colormap, access, save=True,
                                        user=self.getCurrentUser())
