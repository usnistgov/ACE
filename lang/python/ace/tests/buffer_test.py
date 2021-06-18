from ace.rtsp import FrameBuffer

def get_test_buffer(realtime=True):
    buff = FrameBuffer(realtime=realtime)
    for i in range(50):
        buff.push("foo"+ str(i))
    return buff

def test():
    buff = get_test_buffer()
    print(buff.pop(10))
    print(buff.pop(10))

    buff = get_test_buffer(realtime=False)
    print(buff.pop(10))
    print(buff.pop(10))

    buff = get_test_buffer()
    buff.last_pop = 45
    
    print(buff.pop(10))
    print(buff.pop(5))

if __name__ == "__main__":
    test()