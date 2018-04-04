import { restRequest } from 'girder/rest';

import AccessControlledModel from 'girder/models/AccessControlledModel';

var OverlayModel = AccessControlledModel.extend({
    resourceName: 'overlay',

    save: function () {
        if (this.altUrl === null && this.resourceName === null) {
            throw new Error('An altUrl or resourceName must be set on the Model.');
        }

        var path, type;
        if (this.has('_id')) {
            path = (this.altUrl || this.resourceName) + '/' + this.get('_id');
            type = 'PUT';
        } else {
            path = (this.altUrl || this.resourceName) + `?itemId=${this.get('itemId')}`;
            type = 'POST';
        }
        /* Don't save attributes which are objects using this call.  For
         * instance, if the metadata of an item has keys that contain non-ascii
         * values, they won't get handled by the rest call. */
        var data = {};
        _.each(this.keys(), function (key) {
            var value = this.get(key);
            if (!_.isObject(value)) {
                data[key] = value;
            }
        }, this);

        return restRequest({
            url: path,
            method: type,
            contentType: 'application/json',
            processData: false,
            data: JSON.stringify(data)
        }).done((resp) => {
            this.set(resp);
            this.trigger('g:saved');
        }).fail((err) => {
            this.trigger('g:error', err);
        });
    },
});

export default OverlayModel
