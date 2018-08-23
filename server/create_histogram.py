import json
import PIL.Image
import numpy

PIL.Image.MAX_IMAGE_PIXELS = 10000000000

in_path = in_path   # noqa
label = label   # noqa
bins = bins   # noqa
bitmask = bitmask   # noqa

try:
    image = PIL.Image.open(in_path)
except:
    import pytiff
    image = pytiff.Tiff(in_path)
else:
    if image.mode not in ('1', 'L', 'P', 'I', 'F'):
        raise ValueError('invalid image type for histogram: %s' % image.mode)

array = numpy.array(image)
if label:
    array = array[numpy.nonzero(array)]

# TODO: integer histogram optimizations
#if array.dtype == numpy.uint8 and bins == 256:
#    _bins = range(bins + 1)
#else:
#    _bins = bins

if bitmask:
    hist = numpy.zeros(array.dtype.itemsize*8 + 1 - label)
    if not label:
        hist[0] = (array == 0).sum()
    binEdges = numpy.arange(label, hist.shape[0] + label)
    for i in range(1, hist.shape[0] + label):
        hist[i - label] = (array & 1 << i - 1 > 0).sum()
else:
    hist, binEdges = numpy.histogram(array, bins=bins)

#nonzero = numpy.nonzero(hist)
histogram = json.dumps({
    'label': label,
    'bitmask': bitmask,
    'bins': bins,
    #'hist': list(hist[nonzero]),
    #'binEdges': list(binEdges[nonzero]),
    'hist': list(hist),
    'binEdges': list(binEdges),
})

# # TODO: implement RGB(A)
# result = {}
# for i, channel in enumerate(('red', 'green', 'blue')):
#     hist, binEdges = numpy.histogram(array[:, :, i],
#                                       **histogram_kwargs)
#     result[channel] = {
#         'values': list(hist),
#         'bins': list(binEdges),
#     }
