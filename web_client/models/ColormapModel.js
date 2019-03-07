import AccessControlledModel from 'girder/models/AccessControlledModel';
import { restRequest } from 'girder/rest';

var ColormapModel = AccessControlledModel.extend({
    resourceName: 'colormap',

    save: function () {
        var colormap = this.get('colormap');
        this.set('colormap', JSON.stringify(colormap), {silent: true});
        var labels = this.get('labels');
        this.set('labels', JSON.stringify(colormap), {silent: true});
        var promise = AccessControlledModel.prototype.save.call(this, arguments);
        this.set({ colormap: colormap, labels: labels }, {silent: true});
        return promise;
    }
});

export default ColormapModel;
