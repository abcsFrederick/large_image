import _ from 'underscore';
import Backbone from 'backbone';
// Import hammerjs for geojs touch events
import Hammer from 'hammerjs';
import d3 from 'd3';

import { staticRoot, restRequest } from 'girder/rest';
import events from 'girder/events';

import ImageViewerWidget from './base';
import convertAnnotation from '../../annotations/geojs/convert';

window.hammerjs = Hammer;
window.d3 = d3;

/**
 * Generate a new "random" element id (24 random 16 digits).
 */
function guid() {
    function s4() {
        return Math.floor((1 + Math.random()) * 0x10000)
            .toString(16)
            .substring(1);
    }
    return s4() + s4() + s4() + s4() + s4() + s4();
}

var GeojsImageViewerWidget = ImageViewerWidget.extend({
    initialize: function (settings) {
        this._annotations = {};
        this._featureOpacity = {};
        this._globalAnnotationOpacity = settings.globalAnnotationOpacity || 1.0;
        this._globalOverlaysOpacity = settings.globalOverlaysOpacity || 1.0;
        this._globalAnnotationFillOpacity = settings.globalAnnotationFillOpacity || 1.0;
        this._highlightFeatureSizeLimit = settings.highlightFeatureSizeLimit || 10000;
        this._overlays = [];
        this.listenTo(events, 's:widgetDrawRegion', this.drawRegion);
        this.listenTo(events, 'g:startDrawMode', this.startDrawMode);
        this._hoverEvents = settings.hoverEvents;
        this._scale = settings.scale;

        $.when(
            ImageViewerWidget.prototype.initialize.call(this, settings).then(() => {
                if (this.metadata.geospatial) {
                    this.tileWidth = this.tileHeight = null;
                    return restRequest({
                        type: 'GET',
                        url: 'item/' + this.itemId + '/tiles',
                        data: {projection: 'EPSG:3857'}
                    }).done((resp) => {
                        this.levels = resp.levels;
                        this.tileWidth = resp.tileWidth;
                        this.tileHeight = resp.tileHeight;
                        this.sizeX = resp.sizeX;
                        this.sizeY = resp.sizeY;
                        this.metadata = resp;
                    });
                }
                return this;
            }),
            $.ajax({ // like $.getScript, but allow caching
                url: staticRoot + '/built/plugins/large_image/extra/geojs.js',
                dataType: 'script',
                cache: true
            }))
            .done(() => {
                this.trigger('g:beforeFirstRender', this);
                this.render();
            });
    },

    render: function () {
        // If script or metadata isn't loaded, then abort
        if (!window.geo || !this.tileWidth || !this.tileHeight || this.deleted) {
            return this;
        }

        if (this.viewer) {
            // don't rerender the viewer
            return this;
        }

        var geo = window.geo; // this makes the style checker happy

        var params;
        if (!this.metadata.geospatial || !this.metadata.bounds) {
            var w = this.sizeX, h = this.sizeY;
            params = geo.util.pixelCoordinateParams(
                this.el, w, h, this.tileWidth, this.tileHeight);
            params.layer.useCredentials = true;
            params.layer.url = this._getTileUrl('{z}', '{x}', '{y}');
            this.viewer = geo.map(params.map);
            this.viewer.createLayer('osm', params.layer).name('image');
        } else {
            params = {
                keepLower: false,
                attribution: null,
                url: this._getTileUrl('{z}', '{x}', '{y}', {'encoding': 'PNG', 'projection': 'EPSG:3857'}),
                useCredentials: true,
                maxLevel: this.levels - 1
            };
            // the metadata levels is the count including level 0, so use one
            // less than the value specified
            this.viewer = geo.map({node: this.el, max: this.levels - 1});
            this.viewer.bounds({
                left: this.metadata.bounds.xmin,
                right: this.metadata.bounds.xmax,
                top: this.metadata.bounds.ymax,
                bottom: this.metadata.bounds.ymin
            }, 'EPSG:3857');
            this.viewer.createLayer('osm').name('blank');
            this.viewer.createLayer('osm', params).name('image');
        }
        this.viewer.geoOn(geo.event.pan, () => {
            this.setBounds();
        });
        if (this._scale && (this.metadata.mm_x || this.metadata.geospatial || this._scale.scale)) {
            if (!this._scale.scale && !this.metadata.geospatial) {
                // convert mm to m.
                this._scale.scale = this.metadata.mm_x / 1000;
            }
            this.uiLayer = this.viewer.createLayer('ui');
            this.scaleWidget = this.uiLayer.createWidget('scale', this._scale);
        }

        this.setGlobalOverlayOpacity(this._globalOverlaysOpacity);

        // the feature layer is for annotations that are loaded
        this.featureLayer = this.viewer.createLayer('feature', {
            features: ['point', 'line', 'polygon']
        });
        this.setGlobalAnnotationOpacity(this._globalAnnotationOpacity);
        this.setGlobalAnnotationFillOpacity(this._globalAnnotationFillOpacity);
        // the annotation layer is for annotations that are actively drawn
        this.annotationLayer = this.viewer.createLayer('annotation', {
            annotations: ['point', 'line', 'rectangle', 'polygon'],
            showLabels: false
        });

        this.trigger('g:imageRendered', this);
        return this;
    },

    destroy: function () {
        if (this.viewer) {
            // make sure there is nothing left in the animation queue
            var queue = [];
            this.viewer.animationQueue(queue);
            queue.splice(0, queue.length);
            this.viewer.exit();
            this.viewer = null;
        }
        this.deleted = true;
        ImageViewerWidget.prototype.destroy.call(this);
    },

    annotationAPI: _.constant(true),

    /**
     * Render an annotation model on the image.  Currently,
     * this is limited to annotation types that can be directly
     * converted into geojson primatives.
     *
     * Internally, this generates a new feature layer for the
     * annotation that is referenced by the annotation id.
     * All "elements" contained inside this annotations are
     * drawn in the referenced layer.
     *
     * @param {AnnotationModel} annotation
     * @param {object} [options]
     * @param {boolean} [options.fetch=true]
     *   Enable fetching the annotation from the server, including paging
     *   the results.  If false, it is assumed the elements already
     *   exist on the annotation object.  This is useful for temporarily
     *   showing annotations that are not propagated to the server.
     */
    drawAnnotation: function (annotation, options) {
        var geo = window.geo;
        options = _.defaults(options || {}, {fetch: true});
        var geojson = annotation.geojson();
        var present = _.has(this._annotations, annotation.id);
        if (present) {
            _.each(this._annotations[annotation.id].features, (feature) => {
                this.featureLayer.deleteFeature(feature);
            });
        }
        this._annotations[annotation.id] = {
            features: [],
            options: options,
            annotation: annotation
        };
        if (options.fetch && (!present || annotation.refresh())) {
            annotation.off('g:fetched', null, this).on('g:fetched', () => {
                // Trigger an event indicating to the listener that
                // mouseover states should reset.
                this.trigger(
                    'g:mouseResetAnnotation',
                    annotation
                );
                this.drawAnnotation(annotation);
            }, this);
            this.setBounds({[annotation.id]: this._annotations[annotation.id]});
        }
        annotation.refresh(false);
        var featureList = this._annotations[annotation.id].features;
        this._featureOpacity[annotation.id] = {};
        geo.createFileReader('jsonReader', {layer: this.featureLayer})
            .read(geojson, (features) => {
                _.each(features || [], (feature) => {
                    var events = geo.event.feature;
                    featureList.push(feature);

                    feature.selectionAPI(this._hoverEvents);

                    feature.geoOn(
                        [
                            events.mouseclick,
                            events.mouseoff,
                            events.mouseon,
                            events.mouseover,
                            events.mouseout
                        ],
                        (evt) => this._onMouseFeature(evt)
                    );

                    // store the original opacities for the elements in each feature
                    const data = feature.data();
                    if (data.length <= this._highlightFeatureSizeLimit) {
                        this._featureOpacity[annotation.id][feature.featureType] = feature.data()
                            .map(({id, properties}) => {
                                return {
                                    id,
                                    fillOpacity: properties.fillOpacity,
                                    strokeOpacity: properties.strokeOpacity
                                };
                            });
                    }
                });
                this._mutateFeaturePropertiesForHighlight(annotation.id, features);
                this.viewer.draw();
            });
    },

    /**
     * Highlight the given annotation/element by reducing the opacity of all
     * other elements by 75%.  For performance reasons, features with a large
     * number of elements are not modified.  The limit for this behavior is
     * configurable via the constructor option `highlightFeatureSizeLimit`.
     *
     * Both arguments are optional.  If no element is provided, then all
     * elements in the given annotation are highlighted.  If no annotation
     * is provided, then highlighting state is reset and the original
     * opacities are used for all elements.
     *
     * @param {string?} annotation The id of the annotation to highlight
     * @param {string?} element The id of the element to highlight
     */
    highlightAnnotation: function (annotation, element) {
        this._highlightAnnotation = annotation;
        this._highlightElement = element;
        _.each(this._annotations, (layer, annotationId) => {
            const features = layer.features;
            this._mutateFeaturePropertiesForHighlight(annotationId, features);
        });
        this.viewer.scheduleAnimationFrame(this.viewer.draw);
        return this;
    },

    /**
     * Use geojs's `updateStyleFromArray` to modify the opacities of all elements
     * in a feature.  This method uses the private attributes `_highlightAnntotation`
     * and `_highlightElement` to determine which element to modify.
     */
    _mutateFeaturePropertiesForHighlight: function (annotationId, features) {
        _.each(features, (feature) => {
            const data = this._featureOpacity[annotationId][feature.featureType];
            if (!data) {
                // skip highlighting code on features with a lot of entities because
                // this slows down interactivity considerably.
                return;
            }
            // pre-allocate arrays for performance
            const fillOpacityArray = new Array(data.length);
            const strokeOpacityArray = new Array(data.length);

            for (let i = 0; i < data.length; i += 1) {
                const id = data[i].id;
                const fillOpacity = data[i].fillOpacity * this._globalAnnotationFillOpacity;
                const strokeOpacity = data[i].strokeOpacity;
                if (!this._highlightAnnotation ||
                    (!this._highlightElement && annotationId === this._highlightAnnotation) ||
                    this._highlightElement === id) {
                    fillOpacityArray[i] = fillOpacity;
                    strokeOpacityArray[i] = strokeOpacity;
                } else {
                    fillOpacityArray[i] = fillOpacity * 0.25;
                    strokeOpacityArray[i] = strokeOpacity * 0.25;
                }
            }

            feature.updateStyleFromArray('fillOpacity', fillOpacityArray);
            feature.updateStyleFromArray('strokeOpacity', strokeOpacityArray);
        });
    },

    /**
     * When the image visible bounds change, or an annotation is first created,
     * set the view information for any annotation which requires it.
     *
     * @param {object} [annotations] If set, a dictionary where the keys are
     *      annotation ids and the values are an object which includes the
     *      annotation options and a reference to the annotation.  If not
     *      specified, use `this._annotations` and update the view for all
     *      relevant annotatioins.
     */
    setBounds: function (annotations) {
        var zoom = this.viewer.zoom(),
            bounds = this.viewer.bounds(),
            zoomRange = this.viewer.zoomRange();
        _.each(annotations || this._annotations, (annotation) => {
            if (annotation.options.fetch && annotation.annotation.setView) {
                annotation.annotation.setView(bounds, zoom, zoomRange.max);
            }
        });
    },

    /**
     * Remove an annotation from the image.  This simply
     * finds a layer with the given id and removes it because
     * each annotation is contained in its own layer.  If
     * the annotation is not drawn, this is a noop.
     *
     * @param {AnnotationModel} annotation
     */
    removeAnnotation: function (annotation) {
        annotation.off('g:fetched', null, this);
        // Trigger an event indicating to the listener that
        // mouseover states should reset.
        this.trigger(
            'g:mouseResetAnnotation',
            annotation
        );
        if (_.has(this._annotations, annotation.id)) {
            _.each(this._annotations[annotation.id].features, (feature) => {
                this.featureLayer.deleteFeature(feature);
            });
            delete this._annotations[annotation.id];
            delete this._featureOpacity[annotation.id];
            this.featureLayer.draw();
        }
    },

    _setOverlayVisibility: function (index, visible, exclude) {
        if (visible === undefined || visible === null) {
            visible = this._overlays[index].overlay.get('displayed');
        }
        if (exclude === undefined || exclude === null) {
            exclude = this._overlays[index].overlay.get('exclude');
        }
        var updatedLayers = [];
        _.each(this._overlays[index].layers, (layer, bin) => {
            bin = parseInt(bin);
            var layerVisible = _.contains(exclude, bin) ? false : visible;
            if (layerVisible != layer.visible()) {
                layer.visible(layerVisible);
                updatedLayers.push(bin);
            }
        });
        return updatedLayers;
    },

    _setOverlayLayerVisibility: function (index, layer, visible) {
        this._overlays[index].layers[layer].visible(overlay.get('displayed') ? visible : false);
    },

    _addOverlay: function (overlay) {
        var geo = window.geo;
        var index = overlay.get('index');

        var queries = [];
        if (overlay.get('bitmask')) {
            var colormapId = overlay.get('colormapId');
            var threshold = overlay.get('threshold');
            threshold = threshold ? threshold : {min: 0, max: 8};

            var i = Math.max(overlay.get('label') ? 1 : 0, threshold.min);
            for (; i <= threshold.max; i++) {
                var query = { bitmaskChannel: i };
                if (colormapId) {
                    query['colormapId'] = colormapId;
                }
                queries.push(query);
            }
        } else {
            var query = {};
            if (overlay.get('label')) {
                query['label'] = 1;
                if (!overlay.get('invertLabel')) {
                    query['invertLabel'] = 0;
                }
                if (overlay.get('flattenLabel')) {
                    query['flattenLabel'] = 1;
                }
            }
            var threshold = overlay.get('threshold');
            if (threshold) {
                query['normalize'] = 1;
                if (threshold.min != null) {
                    query['normalizeMin'] = threshold.min;
                }
                if (threshold.max != null) {
                    query['normalizeMax'] = threshold.max;
                }
            }
            var colormapId = overlay.get('colormapId');
            if (colormapId) {
                query['colormapId'] = colormapId;
            }
            queries.push(query);
        }

        this._overlays[index] = {
            overlay: overlay,
            layers: {}
        };

        var opacities = overlay.get('opacities') || [];

        _.each(queries, (query) => {
            var params = geo.util.pixelCoordinateParams(this.el,
                                                        this.sizeX, this.sizeY,
                                                        this.tileWidth, this.tileHeight);
            params.layer.useCredentials = true;
            //params.layer.keepLower = false;
            params.layer.url = this._getTileUrl('{z}', '{x}', '{y}',
                                                query, overlay.get('overlayItemId'));

            params.layer.visible = overlay.get('displayed') && !(overlay.get('exclude') && _.contains(overlay.get('exclude'), query.bitmaskChannel));
            var maxZoom = this.viewer.zoomRange().max;
            var offset = overlay.get('offset');
            params.layer.tileOffset = (level) => {
                var scale = Math.pow(2, level - maxZoom);
                return {x: -offset.x*scale, y: -offset.y*scale};
            };
            var geojsLayer = this.viewer.createLayer('osm', params.layer)
            geojsLayer.name('overlay');
            geojsLayer.zIndex(this.featureLayer.zIndex());
            var bin = query.bitmaskChannel ? query.bitmaskChannel : 0;
            geojsLayer.opacity(this._globalOverlaysOpacity * overlay.get('opacity') * (opacities[bin] === undefined ? 1 : opacities[bin]));
            this._overlays[index].layers[bin] = geojsLayer;
        });

        this._setOverlayVisibility(index, overlay.get('displayed'));

        return index;
    },

    _removeOverlay: function(index) {
        _.each(this._overlays[index].layers, (layer) => {
            this.viewer.deleteLayer(layer);
        });
        delete this._overlays[index];
    },

    removeOverlay: function(overlay) {
        var index = overlay.get('index');
        if (_.has(this._overlays, index)) {
           this._removeOverlay(index);
           this.viewer.draw();
        }
    },

    //updateOverlay: function(overlay) {
    drawOverlay: function(overlay) {
        var index = overlay.get('index');
        if (_.has(this._overlays, index)) {
            this._removeOverlay(index);
        }
        index = this._addOverlay(overlay);
        this.redrawOverlay(index);
        return index;
    },

    redrawOverlay: function(index, layers) {
        if (layers) {
            _.each(layers, (layer) => {
                this._overlays[index].layers[layer].draw();
            });
        } else {
            _.each(this._overlays[index].layers, (layer) => { layer.draw(); });
        }
    },

    redrawOverlayLayer: function(index, layer) {
        this._overlays[index].layer[layer].draw();
    },

    setOverlayVisibility: function (index, visible) {
        var updatedLayers = this._setOverlayVisibility(index, visible);
        this.redrawOverlay(index, updatedLayers);
    },

    setOverlayLayerVisibility: function (index, layer, visible) {
        this._setOverlayVisibility(index, layer, visible);
        this.redrawOverlayLayer(index, layer);
    },

    moveOverlayDown: function (index) {
        var _overlay = this._overlays[index];
        var newIndex = _overlay.overlay.get('index');
        this._overlays[index] = this._overlays[newIndex];
        this._overlays[newIndex] = _overlay;
        _.each(_overlay.layers, (layer) => {
            layer.moveUp(this._overlays[index].layers.length);
        });
        this.viewer.draw();
    },

    moveOverlayUp: function (index) {
        var _overlay = this._overlays[index];
        var newIndex = _overlay.overlay.get('index');
        this._overlays[index] = this._overlays[newIndex];
        this._overlays[newIndex] = _overlay;
        _.each(_overlay.layers, (layer) => {
            layer.moveDown(this._overlays[index].layers.length);
        });
        this.viewer.draw();
    },

    getOverlayLayerValues: function (index, layers, x, y, width, height) {
        if (!this._overlays || !this._overlays[index]) {
            return $.when();
        }
        layers = layers || _.keys(this._overlays[index].layers);
        x = x || 0;
        y = y || 0;
        width = width || 1;
        height = height || 1;

        var opts = { background: false, wait: 'idle' };

        var promises = _.map(layers, (layerIndex) => {
            var layer = this._overlays[index].layers[layerIndex];
            return this.viewer.screenshot(layer, 'canvas', null, opts).then((canvas) => {
                return canvas.getContext('2d').getImageData(x, y, 1, 1).data;
            });
        }); 

        return $.when.apply($, promises).then(function () {
            var indexedValues = [];
            _.each(arguments, (value, i) => {
                indexedValues[layers[i]] = value;
            });
            return indexedValues;
        });
    },

    /**
     * Set the image interaction mode to region drawing mode.  This
     * method takes an optional `model` argument where the region will
     * be stored when created by the user.  In any case, this method
     * returns a promise that resolves to an array defining the region:
     *   [ left, top, width, height ]
     *
     * @param {Backbone.Model} [model] A model to set the region to
     * @returns {$.Promise}
     */
    drawRegion: function (model) {
        model = model || new Backbone.Model();
        return this.startDrawMode('rectangle', {trigger: false}).then((elements) => {
            /*
             * Strictly speaking, the rectangle drawn here could be rotated, but
             * for simplicity we will set the region model assuming it is not.
             * To be more precise, we could expand the region to contain the
             * whole rotated rectangle.  A better solution would be to add
             * a draw parameter to geojs that draws a rectangle aligned with
             * the image coordinates.
             */
            var element = elements[0];
            var width = Math.round(element.width);
            var height = Math.round(element.height);
            var left = Math.round(element.center[0] - element.width / 2);
            var top = Math.round(element.center[1] - element.height / 2);

            model.set('value', [
                left, top, width, height
            ], {trigger: true});

            return model.get('value');
        });
    },

    /**
     * Set the image interaction mode to draw the given type of annotation.
     *
     * @param {string} type An annotation type, or null to turn off drawing.
     * @param {object} [options]
     * @param {boolean} [options.trigger=true]
     *      Trigger a global event after creating each annotation element.
     * @returns {$.Promise}
     *      Resolves to an array of generated annotation elements.
     */
    startDrawMode: function (type, options) {
        var layer = this.annotationLayer;
        var elements = [];
        var annotations = [];
        var defer = $.Deferred();
        var element;

        layer.mode(null);
        layer.geoOff(window.geo.event.annotation.state);
        layer.removeAllAnnotations();

        options = _.defaults(options || {}, {trigger: true});
        layer.geoOn(
            window.geo.event.annotation.state,
            (evt) => {
                if (evt.annotation.state() !== window.geo.annotation.state.done) {
                    return;
                }
                element = convertAnnotation(evt.annotation);
                if (!element.id) {
                    element.id = guid();
                }
                elements.push(element);
                annotations.push(evt.annotation);

                if (options.trigger) {
                    events.trigger('g:annotationCreated', element, evt.annotation);
                }

                layer.removeAllAnnotations();
                layer.geoOff(window.geo.event.annotation.state);
                defer.resolve(elements, annotations);
            }
        );
        layer.mode(type);
        return defer.promise();
    },

    setGlobalAnnotationOpacity: function (opacity) {
        this._globalAnnotationOpacity = opacity;
        if (this.featureLayer) {
            this.featureLayer.opacity(opacity);
        }
        return this;
    },

    setGlobalOverlayOpacity: function (opacity) {
        this._globalOverlaysOpacity = opacity;
        _.each(this._overlays, (_overlay) => {
            if (!_overlay) {
                return;
            }
            var opacity = _overlay.overlay.get('opacity');
            var opacities = _overlay.overlay.get('opacities') || [];
            _.each(_overlay.layers, (layer, i) => {
                layer.opacity(this._globalOverlaysOpacity * opacity * (opacities[i] === undefined ? 1 : opacities[i]));
            });
        });

        if (this.viewer) {
            this.viewer.draw();
        }

        return this;
    },

    //setOverlayOpacity: function (index, opacity) {
    setOverlayOpacity: function (index) {
        var _overlay = this._overlays[index];
        var opacity = _overlay.overlay.get('opacity');
        var opacities = _overlay.overlay.get('opacities') || [];
        _.each(_overlay.layers, (layer, i) => {
            layer.opacity(this._globalOverlaysOpacity * opacity * (opacities[i] === undefined ? 1 : opacities[i]));
        });
        return this;
    },

    //setOverlayOpacities: function (index, opacities) {
    setOverlayOpacities: function (index) {
        var _overlay = this._overlays[index];
        var opacity = _overlay.overlay.get('opacity');
        var opacities = _overlay.overlay.get('opacities') || [];
        _.each(_overlay.layers, (layer, i) => {
            layer.opacity(this._globalOverlaysOpacity * opacity * (opacities[i] === undefined ? 1 : opacities[i]));
        });
        return this;
    },

    setGlobalAnnotationFillOpacity: function (opacity) {
        this._globalAnnotationFillOpacity = opacity;
        if (this.featureLayer) {
            _.each(this._annotations, (layer, annotationId) => {
                const features = layer.features;
                this._mutateFeaturePropertiesForHighlight(annotationId, features);
            });
            this.featureLayer.draw();
        }
        return this;
    },

    _setEventTypes: function () {
        var events = window.geo.event.feature;
        this._eventTypes = {
            [events.mouseclick]: 'g:mouseClickAnnotation',
            [events.mouseoff]: 'g:mouseOffAnnotation',
            [events.mouseon]: 'g:mouseOnAnnotation',
            [events.mouseover]: 'g:mouseOverAnnotation',
            [events.mouseout]: 'g:mouseOutAnnotation'
        };
    },

    _onMouseFeature: function (evt) {
        var properties = evt.data.properties || {};
        var eventType;

        if (!this._eventTypes) {
            this._setEventTypes();
        }

        if (properties.element && properties.annotation) {
            eventType = this._eventTypes[evt.event];

            if (eventType) {
                this.trigger(
                    eventType,
                    properties.element,
                    properties.annotation,
                    evt
                );
            }
        }
    }
});

export default GeojsImageViewerWidget;
