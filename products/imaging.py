"""Image handling for uploaded listing photos.

Phone photos arrive as 4-6 MB files, often several thousand pixels wide and
carrying EXIF metadata that can include the GPS coordinates of where the photo
was taken. Nothing on the site needs more than about 1600px, and nobody should
be publishing their location by accident, so every upload is re-encoded here
before it is stored.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

#: Longest edge we keep. The detail page shows images at about 700px wide, so
#: this leaves room for high-density screens and the lightbox.
MAX_DIMENSION = 1600

#: Minimum width we accept, so cards and the detail page are never blurry.
MIN_WIDTH = 400

#: 5 MB, checked before Pillow opens the file.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

JPEG_QUALITY = 85


class ImageTooSmall(ValueError):
    """The upload is a readable image, but smaller than MIN_WIDTH."""


class ImageTooLarge(ValueError):
    """The upload decodes to far more pixels than any real photo.

    A "decompression bomb": a few kilobytes of highly compressible PNG that
    expands into a bitmap of hundreds of millions of pixels, so the byte-size
    check passes and then Pillow tries to allocate gigabytes. Pillow has its
    own guard (Image.MAX_IMAGE_PIXELS) which raises DecompressionBombError;
    this turns that into a form error instead of a 500.
    """


def process_upload(uploaded, max_dimension=MAX_DIMENSION, min_width=MIN_WIDTH):
    """Re-encode an uploaded image as a clean, downscaled JPEG.

    Returns a ContentFile that can be assigned straight to an ImageField.
    Raises UnidentifiedImageError if the file is not an image Pillow can read
    (which also means a .jpg that is really something else is rejected),
    ImageTooSmall if it is narrower than ``min_width``, or ImageTooLarge if it
    decodes to an implausible number of pixels.
    """
    uploaded.seek(0)
    try:
        opened = Image.open(uploaded)
    except Image.DecompressionBombError as error:
        raise ImageTooLarge(str(error)) from error

    with opened as image:
        # Honour the EXIF orientation flag first: dropping the metadata
        # without this rotates every phone photo onto its side.
        image = ImageOps.exif_transpose(image)

        if image.width < min_width:
            raise ImageTooSmall(image.width)

        if image.width > max_dimension or image.height > max_dimension:
            # thumbnail() keeps the aspect ratio and never scales up.
            image.thumbnail(
                (max_dimension, max_dimension), Image.Resampling.LANCZOS
            )

        if image.mode in ('RGBA', 'LA', 'P'):
            # JPEG has no alpha channel, so flatten onto white.
            flattened = Image.new('RGB', image.size, (255, 255, 255))
            rgba = image.convert('RGBA')
            flattened.paste(rgba, mask=rgba.split()[-1])
            image = flattened
        elif image.mode != 'RGB':
            image = image.convert('RGB')

        buffer = BytesIO()
        # Saving through a fresh buffer with no exif argument is what strips
        # the metadata: Pillow only writes the tags it is given.
        image.save(buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)

    return ContentFile(buffer.getvalue(), name=jpeg_name(uploaded.name))


def jpeg_name(original_name):
    """A .jpg filename based on the uploaded one, since we always re-encode."""
    stem = (original_name or 'photo').rsplit('/', 1)[-1].rsplit('.', 1)[0]
    return f'{stem[:60] or "photo"}.jpg'


__all__ = [
    'ImageTooLarge',
    'ImageTooSmall',
    'MAX_DIMENSION',
    'MAX_UPLOAD_BYTES',
    'MIN_WIDTH',
    'UnidentifiedImageError',
    'process_upload',
]
