from bson.objectid import ObjectId
import json

import cherrypy

from girder import logger
from girder.api import access
from girder.api.describe import describeRoute, autoDescribeRoute, Description
from girder.api.rest import Resource, loadmodel, filtermodel
from girder.constants import AccessType, SortDir
from girder.exceptions import ValidationException, RestException
from girder.models.item import Item
from girder.models.user import User
from ..models.overlay import Overlay

class OverlayResource(Resource):
    def __init__(self):
        super(OverlayResource, self).__init__()

        self.resourceName = 'overlay'
        self.route('GET', (), self.find)
        self.route('POST', (), self.createOverlay)
        self.route('DELETE', (':id',), self.deleteOverlay)
        self.route('GET', (':id',), self.getOverlay)
        self.route('PUT', (':id',), self.updateOverlay)

    @describeRoute(
        Description('Search for overlays.')
        .responseClass('Overlay', array=True)
        .param('itemId', 'The ID of the parent item.',
                         required=False)
        .pagingParams(None, defaultLimit=None)
        .errorResponse()
        .errorResponse('No matching overlays were found.', 404)
    )
    @access.user
    @filtermodel(model='overlay', plugin='large_image')
    def find(self, params):
        user = self.getCurrentUser()
        limit, offset, sort = self.getPagingParameters(params)
        if sort is None:
            sort = [('itemId', SortDir.ASCENDING), ('index', SortDir.ASCENDING)]
        query = {
            'creatorId': user['_id'],
        }
        if 'itemId' in params:
            query['itemId'] = ObjectId(params['itemId'])
        return list(Overlay().filterResultsByPermission(
            cursor=Overlay().find(query, sort=sort),
            user=user,
            level=AccessType.READ,
            limit=limit, offset=offset
        ))

    @describeRoute(
        Description('Create overlay for an item.')
        .responseClass('Overlay')
        .param('body', 'A JSON object containing the overlay.', paramType='body')
        .errorResponse('Parent large image ID was invalid.')
        .errorResponse('Read access was denied for the parent item.', 403)
        .errorResponse('Read access was denied for the overlay item.', 403)
    )
    @access.user
    @filtermodel(model='overlay', plugin='large_image')
    def createOverlay(self, params):
        user = self.getCurrentUser()
        overlay = self.getBodyJson()

        overlay['creatorId'] = user['_id']

        if 'itemId' in overlay:
            item = Item().load(overlay['itemId'], force=True)
            Item().requireAccess(item, user=user, level=AccessType.READ)
            overlay['itemId'] = item['_id']

        if 'overlayItemId' in overlay:
            overlayItem = Item().load(overlay['overlayItemId'], force=True)
            Item().requireAccess(overlayItem, user=user, level=AccessType.READ)
            overlay['overlayItemId'] = overlayItem['_id']

        return Overlay().createOverlay(**overlay)

    @describeRoute(
        Description('Delete an overlay.')
        .param('id', 'The ID of the overlay.', paramType='path')
        .errorResponse('ID was invalid.')
        .errorResponse('Write access was denied for the overlay.', 403)
    )
    @access.user
    @loadmodel(model='overlay', plugin='large_image', level=AccessType.WRITE)
    @filtermodel(model='overlay', plugin='large_image')
    def deleteOverlay(self, overlay, params):
        user = self.getCurrentUser()
        if overlay['creatorId'] != user['_id']:
            raise RestException('Invalid overlay for user', 403)
        Overlay().remove(overlay)

    @describeRoute(
        Description('Get overlay by ID.')
        .param('id', 'The ID of the overlay.', paramType='path')
        .errorResponse('ID was invalid.')
        .errorResponse('Read access was denied for the overlay.', 403)
        .errorResponse('Overlay not found.', 404)
    )
    @access.cookie
    @access.public
    @loadmodel(model='overlay', plugin='large_image', level=AccessType.READ)
    @filtermodel(model='overlay', plugin='large_image')
    def getOverlay(self, overlay, params):
        user = self.getCurrentUser()
        if overlay['creatorId'] != user['_id']:
            raise RestException('Invalid overlay for user', 403)
        return overlay

    @describeRoute(
        Description('Update an overlay.')
        .param('id', 'The ID of the overlay.', paramType='path')
        .param('body', 'A JSON object containing the overlay.',
               paramType='body')
        .errorResponse('Write access was denied for the item.', 403)
        .errorResponse('Overlays not found.', 404)
    )
    @access.user
    @loadmodel(model='overlay', plugin='large_image', level=AccessType.WRITE)
    @filtermodel(model='overlay', plugin='large_image')
    def updateOverlay(self, overlay, params):
        user = self.getCurrentUser()
        update = self.getBodyJson()
        if overlay['creatorId'] != user['_id']:
            raise RestException('Invalid overlay for user', 403)
        if 'creatorId' in update:
            if ObjectId(update['creatorId']) != user['_id']:
                raise RestException('Cannot change overlay user', 403)
            del update['creatorId']
        if 'itemId' in update:
            item = Item().load(update['itemId'], force=True)
            if item is not None:
                Item().requireAccess(item, user=user, level=AccessType.READ)
            	update['itemId'] = item['_id']
        if 'overlayItemId' in update:
            overlayItem = Item().load(update['overlayItemId'], force=True)
            Item().requireAccess(overlayItem, user=user, level=AccessType.READ)
            update['overlayItemId'] = overlayItem['_id']
        if '_id' in update:
            del update['_id']
        return Overlay().updateOverlay(overlay, update)
