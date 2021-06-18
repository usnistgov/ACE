import numpy as np

from ace.rtsp import FrameBuffer
from ace.analytichandler import FrameHandler, BatchHandler

from pprint import pprint

def _get_frame_handler(frame_batch_obj):
    return FrameHandler(frame_batch_obj=frame_batch_obj, stream_addr="test-stream", session_id="frame-handler-test")

def _get_frame_batch_handler(frame_batch_obj):
    return BatchHandler(frame_batch_obj=frame_batch_obj, stream_addr="test-stream", session_id="frame-handler-test")

def get_frame_buffer(num):
    buff = FrameBuffer()
    for i in range(50):
        buff.push(np.zeros((25,25, 3))+i)
    frame_batch_obj = buff.pop(num)
    return frame_batch_obj

def get_frame_handler():
    frame_batch_obj = get_frame_buffer(1)
    return _get_frame_handler(frame_batch_obj=frame_batch_obj)

def get_frame_batch_handler():
    frame_batch_obj = get_frame_buffer(16)
    return _get_frame_batch_handler(frame_batch_obj=frame_batch_obj)

def test_batch():
    handler = get_frame_batch_handler()
    handler.set_start_time()
    frames = handler.get_frame_batch()

    handler.set_name("test-analytic")
    handler.add_bounding_box(classification="bounding-box-test-all", confidence=0.77, x1=1, x2=2, y1=3, y2=4)
    handler.add_bounding_box(classification="bounding-box-test-frame", confidence=0.33, x1=5, x2=6, y1=7, y2=8, frame_index=5)
    handler.add_filter("power", 9000)
    handler.add_tags(thing="this", time="now", test=True, seven=7)
    handler.set_end_time()
    resp = handler.get_response(include_frame=True)
    pprint(resp)

def test_single():
    handler = get_frame_handler()
    handler.set_start_time()
    frames = handler.get_frame()

    handler.set_name("test-analytic")
    handler.add_bounding_box(classification="bounding-box-test-all", confidence=0.77, x1=1, x2=2, y1=3, y2=4)
    handler.add_filter("power", 9000)
    handler.add_tags(thing="this", time="now", test=True, seven=7)
    handler.set_end_time()
    resp = handler.get_response(include_frame=True)
    pprint(resp)
def test():
    test_batch()
    print("\n*********Testing single frame********\n")
    test_single()

if __name__ == "__main__":
    test()