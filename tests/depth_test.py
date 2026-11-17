#
# These tests cover the explicit bit-depth pipeline: 10-bit pass-through,
# 8-bit to 10-bit upconversion, mixed-depth batch handling, and the
# failure/cleanup behavior of the explicit depth path.
#
import inspect
import os
import threading

from pytest import mark, raises

from wand.exceptions import WandRuntimeError
from wand.image import BIT_DEPTH_LIMITED_FORMATS, Image, LOGGER
from wand.version import QUANTUM_DEPTH


def make_gradient(width=64, height=64, depth=None):
    img = Image(width=width, height=height, pseudo='gradient:')
    if depth is not None:
        img.depth = depth
    return img


def row_samples(img, y=0):
    return img.export_pixels(0, y, img.width, 1, channel_map='R',
                             storage='quantum')


def column_samples(img, x=32):
    return img.export_pixels(x, 0, 1, img.height, channel_map='R',
                             storage='quantum')


def test_passthrough_10bit(tmp_path):
    src = str(tmp_path / 'src10.png')
    dst = str(tmp_path / 'dst10.png')
    with make_gradient(1024, 64, depth=10) as img:
        img.validate_depth(expected=10)
        img.save(filename=src)
    with Image(filename=src) as img:
        img.save(filename=dst, depth='auto')
    with Image(filename=src) as a, Image(filename=dst) as b:
        assert b.depth > 8
        assert a.signature == b.signature
        b.validate_depth(expected=10)


def test_passthrough_10bit_file_object(tmp_path):
    with make_gradient(256, 64, depth=10) as img:
        img.format = 'png'
        with open(str(tmp_path / 'out.png'), 'w+b') as fp:
            img.save(file=fp, depth=10)
    with Image(filename=str(tmp_path / 'out.png')) as img:
        assert img.depth > 8


def test_upgrade_8bit_to_10bit(tmp_path):
    dst = str(tmp_path / 'up10.png')
    with make_gradient(64, 1024, depth=8) as img:
        src_column = column_samples(img)
        img.save(filename=dst, depth=10)
    with Image(filename=dst) as img:
        assert img.depth > 8
        out_column = column_samples(img)
    # 8-bit values scaled to 10-bit must stay monotonic, and each output
    # sample must land within one 10-bit step of the source value.
    assert len(set(out_column)) >= len(set(src_column))
    assert all(b <= a for a, b in zip(out_column, out_column[1:]))
    for before, after in zip(src_column, out_column):
        assert abs(after - before) <= 64


def test_upgrade_8bit_to_10bit_dither_configurable(tmp_path):
    for dither in ('no', 'floyd_steinberg', 'riemersma'):
        dst = str(tmp_path / 'up10_{0}.png'.format(dither))
        with make_gradient(256, 64, depth=8) as img:
            img.save(filename=dst, depth=10, dither=dither)
        with Image(filename=dst) as img:
            assert img.depth > 8


def test_mixed_depth_batch(tmp_path):
    depths = (8, 10, 8, 10)
    for index, depth in enumerate(depths):
        with make_gradient(256, 64, depth=depth) as img:
            img.save(filename=str(tmp_path / 'item{0}.png'.format(index)),
                     depth='auto')
    for index, depth in enumerate(depths):
        with Image(filename=str(tmp_path / 'item{0}.png'.format(index))) as img:
            if depth > 8:
                assert img.depth > 8
            else:
                assert img.depth == 8


def test_mixed_depth_directory(tmp_path):
    src_dir = tmp_path / 'src'
    out_dir = tmp_path / 'out'
    src_dir.mkdir()
    out_dir.mkdir()
    expected = {}
    for index, depth in enumerate((10, 8, 10, 8)):
        name = 'mixed{0}.png'.format(index)
        expected[name] = depth
        with make_gradient(256, 64, depth=depth) as img:
            img.save(filename=str(src_dir / name))
    for name in sorted(os.listdir(str(src_dir))):
        with Image(filename=str(src_dir / name)) as img:
            img.save(filename=str(out_dir / name), depth='auto')
    for name, depth in expected.items():
        with Image(filename=str(out_dir / name)) as img:
            if depth > 8:
                assert img.depth > 8
            else:
                assert img.depth == 8


def test_mixed_batch_8bit_items_match_default_save(tmp_path):
    with make_gradient(256, 64, depth=8) as img:
        img.save(filename=str(tmp_path / 'default.png'))
        img.save(filename=str(tmp_path / 'auto.png'), depth='auto')
    with open(str(tmp_path / 'default.png'), 'rb') as fp:
        default_blob = fp.read()
    with open(str(tmp_path / 'auto.png'), 'rb') as fp:
        auto_blob = fp.read()
    assert default_blob == auto_blob


def test_banding_reduced_by_10bit(tmp_path):
    low = str(tmp_path / 'band8.png')
    high = str(tmp_path / 'band10.png')
    with make_gradient(64, 1024, depth=8) as img:
        img.save(filename=low)
    with make_gradient(64, 1024, depth=10) as img:
        img.save(filename=high, depth=10)
    with Image(filename=low) as img:
        low_column = column_samples(img)
    with Image(filename=high) as img:
        high_column = column_samples(img)
    low_steps = [abs(b - a) for a, b in zip(low_column, low_column[1:])]
    high_steps = [abs(b - a) for a, b in zip(high_column, high_column[1:])]
    # 10-bit output holds more levels with smaller steps between neighbors.
    assert len(set(high_column)) > 3 * len(set(low_column))
    assert max(high_steps) < max(low_steps)


def test_10bit_file_size_reasonable(tmp_path):
    low = str(tmp_path / 'size8.png')
    high = str(tmp_path / 'size10.png')
    with make_gradient(1024, 64, depth=8) as img:
        img.save(filename=low)
    with make_gradient(1024, 64, depth=10) as img:
        img.save(filename=high, depth=10)
    ratio = os.path.getsize(high) / float(os.path.getsize(low))
    assert ratio < 2.0


def test_unsupported_format_raises_with_suggestion(tmp_path):
    dst = str(tmp_path / 'out.jpg')
    with make_gradient(64, 64, depth=10) as img:
        with raises(ValueError) as exc_info:
            img.save(filename=dst, depth=10)
    assert 'PNG' in str(exc_info.value)
    assert not os.path.exists(dst)


def test_unsupported_format_covers_common_8bit_codecs():
    for fmt in ('JPEG', 'GIF', 'BMP', 'PNG24', 'WEBP'):
        assert fmt in BIT_DEPTH_LIMITED_FORMATS


def test_failed_write_leaves_no_partial_file(tmp_path, monkeypatch):
    from wand.image import library
    dst = str(tmp_path / 'partial.png')

    def broken_write(wand, filename):
        with open(dst, 'wb') as fp:
            fp.write(b'partial')
        raise OSError('simulated write failure')

    monkeypatch.setattr(library, 'MagickWriteImage', broken_write)
    with make_gradient(64, 64, depth=10) as img:
        with raises(OSError):
            img.save(filename=dst, depth=10)
    assert not os.path.exists(dst)


def test_preexisting_file_not_removed_on_failure(tmp_path, monkeypatch):
    from wand.image import library
    dst = str(tmp_path / 'keep.png')
    with open(dst, 'wb') as fp:
        fp.write(b'original')

    def broken_write(wand, filename):
        raise OSError('simulated write failure')

    monkeypatch.setattr(library, 'MagickWriteImage', broken_write)
    with make_gradient(64, 64, depth=10) as img:
        with raises(OSError):
            img.save(filename=dst, depth=10)
    with open(dst, 'rb') as fp:
        assert fp.read() == b'original'


def test_validate_depth_detects_mismatch():
    with make_gradient(1024, 64, depth=10) as img:
        with raises(WandRuntimeError):
            img.validate_depth(expected=8)
    with make_gradient(256, 64, depth=8) as img:
        assert img.validate_depth(expected=8) == 8
    with make_gradient(256, 64, depth=10) as img:
        assert img.validate_depth(expected=10) == 10


def test_convert_depth_validation():
    with make_gradient(64, 64) as img:
        with raises(ValueError):
            img.convert_depth(QUANTUM_DEPTH + 1)
        with raises(ValueError):
            img.convert_depth(10, dither='not-a-dither')
        with raises(ValueError):
            img.convert_depth(0)


def test_save_dither_requires_depth(tmp_path):
    with make_gradient(64, 64) as img:
        with raises(ValueError):
            img.save(filename=str(tmp_path / 'x.png'),
                     dither='floyd_steinberg')


def test_save_rejects_unknown_depth_keyword(tmp_path):
    with make_gradient(64, 64) as img:
        with raises(ValueError):
            img.save(filename=str(tmp_path / 'x.png'), depth='maximum')


def test_convert_depth_logs_decision(caplog):
    with make_gradient(64, 64, depth=8) as img:
        with caplog.at_level('INFO', logger=LOGGER.name):
            img.convert_depth(10)
    messages = [record.getMessage() for record in caplog.records]
    assert any('depth decision' in message for message in messages)


def test_default_save_has_no_new_params_and_no_logs(caplog, tmp_path):
    params = inspect.signature(Image.save).parameters
    assert params['depth'].default is None
    assert params['dither'].default == 'no'
    with make_gradient(64, 64, depth=8) as img:
        with caplog.at_level('DEBUG', logger=LOGGER.name):
            img.save(filename=str(tmp_path / 'plain.png'))
            blob = img.make_blob('png')
    assert not [record for record in caplog.records
                if record.name == LOGGER.name]
    with open(str(tmp_path / 'plain.png'), 'rb') as fp:
        assert fp.read() == blob


def test_explicit_depth_does_not_mutate_source(tmp_path):
    with make_gradient(64, 64, depth=8) as img:
        signature = img.signature
        img.save(filename=str(tmp_path / 'out.png'), depth=10)
        assert img.depth == 8
        assert img.signature == signature


@mark.slow
def test_long_run_memory_and_tempfile_stability(tmp_path):
    try:
        with open('/proc/self/statm') as fp:
            statm_available = fp.read().strip() != ''
    except OSError:
        statm_available = False

    def rss_bytes():
        with open('/proc/self/statm') as fp:
            pages = int(fp.read().split()[1])
        return pages * os.sysconf('SC_PAGE_SIZE')

    target = str(tmp_path / 'loop.png')
    for _ in range(20):  # warm-up
        with make_gradient(256, 256, depth=10) as img:
            img.save(filename=target, depth=10)
    baseline = rss_bytes() if statm_available else 0
    for _ in range(150):
        with make_gradient(256, 256, depth=10) as img:
            img.save(filename=target, depth=10)
        with Image(filename=target) as img:
            assert img.depth > 8
    if statm_available:
        growth = rss_bytes() - baseline
        assert growth < 16 * 1024 * 1024
    assert sorted(os.listdir(str(tmp_path))) == ['loop.png']
    with make_gradient(64, 64, depth=10) as img:
        with raises(ValueError):
            img.save(filename=str(tmp_path / 'nope.jpg'), depth=10)
    assert sorted(os.listdir(str(tmp_path))) == ['loop.png']


@mark.slow
def test_concurrent_explicit_depth_saves(tmp_path):
    errors = []

    def work(index):
        try:
            with make_gradient(128, 128, depth=10) as img:
                dst = str(tmp_path / 'concurrent{0}.png'.format(index))
                img.save(filename=dst, depth=10)
            with Image(filename=dst) as img:
                assert img.depth > 8
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(os.listdir(str(tmp_path))) == 8
