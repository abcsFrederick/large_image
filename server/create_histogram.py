import json
import PIL.Image
import numpy

PIL.Image.MAX_IMAGE_PIXELS = 10000000000

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

hist, binEdges = numpy.histogram(array, bins=bins)
#nonzero = numpy.nonzero(hist)
histogram = json.dumps({
    'label': label,
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
