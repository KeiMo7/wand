Writing images
==============

You can write an :class:`~wand.image.Image` object into a file or a byte
string buffer (blob) as format what you want.


Convert images to JPEG
----------------------

If you wonder what is image's format, use :attr:`~wand.image.Image.format`
property.

.. sourcecode:: pycon

   >>> image.format
   'JPEG'

The :attr:`~wand.image.Image.format` property is writable, so you can convert
images by setting this property. ::

    from wand.image import Image

    with Image(filename='pikachu.png') as img:
        img.format = 'jpeg'
        # operations to a jpeg image...

If you want to convert an image without any changes of the original,
use :meth:`~wand.image.Image.convert()` method instead::

    from wand.image import Image

    with Image(filename='pikachu.png') as original:
        with original.convert('jpeg') as converted:
            # operations to a jpeg image...
            pass

.. note::

   Support for some of the formats are delegated to libraries or external
   programs. To get a complete listing of which image formats are supported
   on your system, use :program:`identify` command provided by ImageMagick:

   .. sourcecode:: console

      $ identify -list format


Save to file
------------

In order to save an image to a file, use :meth:`~wand.image.Image.save()`
method with the keyword argument ``filename``::

    from wand.image import Image

    with Image(filename='pikachu.png') as img:
        img.format = 'jpeg'
        img.save(filename='pikachu.jpg')

.. note::

    The image format does not affect the file being saved, to save with a given colorspace use::

        from wand.image import Image

        with Image(filename='pikachu.jpg') as img:
            img.format = 'jpeg'
            img.save(filename='PNG24:pikachu.png')

Save to stream
--------------

You can write an image into a output stream (file-like object which implements
:meth:`~file.write()` method) as well. The parameter ``file`` takes a such
object (it also is the first positional parameter of
:meth:`~wand.image.Image.save()` method).

For example, the following code converts :file:`pikachu.png` image into
JPEG, gzips it, and then saves it to :file:`pikachu.jpg.gz`::

    import gzip
    from wand.image import Image

    gz = gzip.open('pikachu.jpg.gz')
    with Image(filename='pikachu.png') as img:
        img.format = 'jpeg'
        img.save(file=gz)
    gz.close()


Get binary string
-----------------

Want just a binary string of the image? Use
:meth:`~wand.image.Image.make_blob()` method so::

    from wand.image import Image

    with Image(filename='pikachu.png') as img:
        img.format = 'jpeg'
        jpeg_bin = img.make_blob()

There's the optional ``format`` parameter as well. So the above example code
can be simpler::

    from wand.image import Image

    with Image(filename='pikachu.png') as img:
        jpeg_bin = img.make_blob('jpeg')


Controlling output bit depth
----------------------------

.. versionadded:: 0.7.3

By default :meth:`~wand.image.Image.save` keeps its historical behavior and
writes whatever depth the image currently holds. High bit-depth pipelines
(for example 10-bit delivery) can instead request an explicit output depth
with the ``depth`` parameter. The image itself is never mutated; the depth
conversion is applied to an internal staging copy::

    from wand.image import Image

    with Image(filename='frame10.png') as img:
        img.save(filename='frame10-out.png', depth=10)

Passing ``depth='auto'`` keeps each image's own depth, which makes mixed
batches decide per item instead of falling back to the lowest depth::

    import os

    for name in os.listdir('mixed-dir'):
        with Image(filename=os.path.join('mixed-dir', name)) as img:
            img.save(filename=os.path.join('out-dir', name), depth='auto')

When reducing depth, a dither strategy can be selected with the ``dither``
parameter (see :const:`~wand.image.DITHER_METHODS`)::

    with Image(filename='frame10.png') as img:
        img.save(filename='frame8.png', depth=8, dither='floyd_steinberg')

Formats that can only store 8-bit samples (see
:const:`~wand.image.BIT_DEPTH_LIMITED_FORMATS`) reject an explicit high
bit-depth request with a :exc:`ValueError` instead of silently truncating
to 8-bit.

Use :meth:`~wand.image.Image.convert_depth` for in-place depth conversion,
and :meth:`~wand.image.Image.validate_depth` to detect inputs whose
declared depth does not match their actual sample values.

Migrating an existing 8-bit pipeline only requires adding the parameter
where high bit-depth output is needed; omitting it keeps the previous
behavior, return values, and exception types unchanged::

    # before: everything was written as-is (8-bit chain)
    img.save(filename='out.png')

    # after: explicit 10-bit output, same call site
    img.save(filename='out.png', depth=10)
