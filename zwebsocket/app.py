import socketserver
from collections import defaultdict
import struct
import base64
import hashlib
from .utils import prepare_data
from .protocol import *
import random
import threading
import functools
from .logger import get_logger

logger = get_logger(__name__)


class Zwebsocket(socketserver.BaseRequestHandler):
    """
     0                   1                   2                   3
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
     +-+-+-+-+-------+-+-------------+-------------------------------+
     |F|R|R|R|opcode|M| Payload len| Extended payload length        |
     |I|S|S|S| (4)  |A| (7)        | (16/64)                        |
     |N|V|V|V|      |S|            | (if payload len==126/127)      |
     | |1|2|3|      |K|            |                                |
     +-+-+-+-+-------+-+-------------+ - - - - - - - - - - - - - - - +
     | Extended payload length continued, if payload len == 127     |
     + - - - - - - - - - - - - - - - +-------------------------------+
     |                              |Masking-key, if MASK set to 1  |
     +-------------------------------+-------------------------------+
     | Masking-key (continued)      | Payload Data                  |
     +-------------------------------- - - - - - - - - - - - - - - - +
     : Payload Data continued ...                                   :
     + - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - +
     | Payload Data continued ...                                   |
     +---------------------------------------------------------------+


     FIN: 1 bit
     Indicates that this is the final fragment in a message. The first
     fragment MAY also be the final fragment.

     RSV1, RSV2, RSV3: 1 bit each
     MUST be 0 unless an extension is negotiated that defines meanings
     for non-zero values. If a nonzero value is received and none of
     the negotiated extensions defines the meaning of such a nonzero
     value, the receiving endpoint MUST _Fail the WebSocket
     Connection_.

     Opcode: 4 bits
     Defines the interpretation of the "Payload data". If an unknown
     opcode is received, the receiving endpoint MUST _Fail the

     WebSocket Connection_. The following values are defined.
     * %x0 denotes a continuation frame
     * %x1 denotes a text frame
     * %x2 denotes a binary frame
     * %x3-7 are reserved for further non-control frames
     * %x8 denotes a connection close
     * %x9 denotes a ping
     * %xA denotes a pong
     * %xB-F are reserved for further control frames

     Mask: 1 bit
     Defines whether the "Payload data" is masked. If set to 1, a
     masking key is present in masking-key, and this is used to unmask
     the "Payload data" as per Section 5.3. All frames sent from
     client to server have this bit set to 1.

     Payload length: 7 bits, 7+16 bits, or 7+64 bits
     The length of the "Payload data", in bytes: if 0-125, that is the
     payload length. If 126, the following 2 bytes interpreted as a
     16-bit unsigned integer are the payload length. If 127, the
     following 8 bytes interpreted as a 64-bit unsigned integer (the
     most significant bit MUST be 0) are the payload length. Multibyte
     length quantities are expressed in network byte order. Note that
     in all cases, the minimal number of bytes MUST be used to encode
     the length, for example, the length of a 124-byte-long string
     can’t be encoded as the sequence 126, 0, 124. The payload length
     is the length of the "Extension data" + the length of the
     "Application data". The length of the "Extension data" may be
     zero, in which case the payload length is the length of the
     "Application data".

     Masking-key: 0 or 4 bytes
     All frames sent from the client to the server are masked by a
     32-bit value that is contained within the frame. This field is
     present if the mask bit is set to 1 and is absent if the mask bit
     is set to 0. See Section 5.3 for further information on client-
     to-server masking.

     Payload data: (x+y) bytes
     The "Payload data" is defined as "Extension data" concatenated
     with "Application data".

     Extension data: x bytes
     The "Extension data" is 0 bytes unless an extension has been
     negotiated. Any extension MUST specify the length of the
     "Extension data", or how that length may be calculated, and how
     the extension use MUST be negotiated during the opening handshake.
     If present, the "Extension data" is included in the total payload
     length.

     Application data: y bytes
     Arbitrary "Application data", taking up the remainder of the frame
     after any "Extension data". The length of the "Application data"
     is equal to the payload length minus the length of the "Extension
     data".

    """
    """
    @Author: zer0e
    """

    pre_handle_urls = defaultdict()
    urls = defaultdict()
    after_handle_urls = defaultdict()
    multi_thread = True

    def __init__(self, request, client_address, server):
        self.headers = None
        self.close = False
        self.recv_len = 8096
        self.GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"  # RFC6455 GUID
        self.pre_handle_urls = self.__class__.pre_handle_urls
        self.urls = self.__class__.urls
        self.after_handle_urls = self.__class__.after_handle_urls
        super().__init__(request, client_address, server)

    def setup(self):
        self.hand_shake()

    def pre_handle(self):
        if self.headers['url'] not in self.pre_handle_urls and \
                self.headers['url'] not in self.urls and \
                self.headers['url'] not in self.after_handle_urls:
            self.send_msg("route not right")
            raise Exception("route not right")
        if self.headers['url'] in self.pre_handle_urls:
            res = self.pre_handle_urls[self.headers['url']](websocket=self)
            # if res is None, pass
            if res is not None and type(res) is bool and not res:
                raise Exception("pre handle failed")

    def handle(self):
        self.pre_handle()
        while True:
            frame = self.request.recv(self.recv_len)
            header, data = self.get_frame_data(frame)
            if header['opcode'] == OP_PING:
                logger.debug('heart beat')
                self.pong()
            elif header['opcode'] == OP_TEXT:
                if self.headers['url'] in self.urls:
                    t = threading.Thread(target=self.urls[self.headers['url']],
                                         kwargs={'websocket': self, 'data': data})
                    t.start()
                    if not self.__class__.multi_thread:
                        t.join()
                else:
                    break
            elif header['opcode'] == OP_CLOSE:
                break

    def after_handle(self):
        if self.headers['url'] in self.after_handle_urls:
            res = self.after_handle_urls[self.headers['url']](websocket=self)
            if res is not None and type(res) is bool and not res:
                raise Exception("after handle failed")

    def finish(self):
        if self.close:
            return
        try:
            self.after_handle()
        except:
            pass
        self.wave_hand()
        self.close = True

    def get_http_headers(self, data):
        """
        get websocket first http header
        :param data: bin data read from socket
        :return:
        """
        header_dict = {}
        data = str(data, encoding='utf-8')
        header, body = data.split("\r\n\r\n", 1)
        header_list = header.split("\r\n")
        for i in range(0, len(header_list)):
            if i == 0:
                if len(header_list[0].split(" ")) == 3:
                    header_dict['method'], header_dict['url'], header_dict['protocol'] = header_list[0].split(" ")
            else:
                k, v = header_list[i].split(":", 1)
                header_dict[k] = v.strip()
        return header_dict

    def get_frame_data(self, frame):
        """
        get websocket frame fin, opcode, payload data
        :return:
        """
        frame = prepare_data(frame)
        frame_header = {
            'fin': frame[0] >> 7,
            'opcode': frame[0] & 15
        }
        payload_len = frame[1] & 127
        if payload_len == 126:
            extend_payload_len = frame[2:4]
            mask = frame[4:8]
            decoded = frame[8:]
        elif payload_len == 127:
            extend_payload_len = frame[2:10]
            mask = frame[10:14]
            decoded = frame[14:]
        else:
            extend_payload_len = None
            mask = frame[2:6]
            decoded = frame[6:]
        bytes_list = bytearray()
        for i in range(len(decoded)):
            chunk = decoded[i] ^ mask[i % 4]
            bytes_list.append(chunk)

        if frame_header['opcode'] == OP_TEXT:
            body = str(bytes_list, encoding='utf-8')
        else:
            body = str(bytes_list)
        logger.debug("frame header: " + str(frame_header) + " data: " + body)
        return frame_header, body

    def _get_send_msg(self, msg, fin=True, op_code=OP_TEXT):
        """
        This method is used to get websocket frames
        :param msg: Ready to send data
        :param fin: websocket fin
        :param op_code: websocket op_code see zwebsocket.protocol
        :return:
        """
        send_msg = b""
        send_msg += struct.pack(">B", (128 if fin else 0) + op_code)
        msg = prepare_data(msg)
        data_length = len(msg)
        if data_length <= 125:
            send_msg += str.encode(chr(data_length))
        elif data_length <= 65535:
            send_msg += struct.pack('b', 126)
            send_msg += struct.pack('>h', data_length)
        elif data_length <= (2 ^ 64 - 1):
            send_msg += struct.pack('b', 127)
            send_msg += struct.pack('>q', data_length)
        else:
            raise RuntimeWarning("payload data to long")
        send_message = send_msg + msg
        return send_message

    def send_msg(self, msg):
        """
        This method is used to send websocket frames
        :param msg: Ready to send data
        :return:
        """
        self.request.sendall(self._get_send_msg(msg))

    def hand_shake(self):
        bin_data = self.request.recv(self.recv_len)
        headers = self.get_http_headers(bin_data)
        self.headers = headers
        print(headers)
        self.check_http_headers()
        http_response_tpl = "HTTP/1.1 101 Switching Protocols\r\n" \
                            "Upgrade: websocket\r\n" \
                            "Connection: Upgrade\r\n" \
                            "Sec-WebSocket-Accept: {}\r\n" \
                            "WebSocket-Location: ws://{}{}\r\n\r\n"
        value = headers['Sec-WebSocket-Key'] + self.GUID
        hand_shake_sha1 = base64.b64encode(hashlib.sha1(value.encode('utf-8')).digest())
        http_response = http_response_tpl.format(hand_shake_sha1.decode('utf-8'), headers['Host'], headers['url'])
        self.request.sendall(bytes(http_response, encoding='utf-8'))

    def check_http_headers(self):
        # check Sec-WebSocket-Version if
        if "Sec-WebSocket-Version" not in self.headers or self.headers['Sec-WebSocket-Version'] != 13:
            pass

    def wave_hand(self, status_code=1000):
        """
        send close frame
        :param status_code: 1000 is closed normally, see protocol.CLOSE_CODES
        :return:
        """
        send_msg = b""
        send_msg += b"\x88"
        send_msg += b"\x02"  # 02 is length
        status = struct.pack(">h", status_code)
        self.request.sendall(send_msg + status)

    def ping(self, data=b''):
        if data is not None:
            data = prepare_data(data)
        if data == b'':
            data = struct.pack("!I", random.getrandbits(32))
        self.request.sendall(self._get_send_msg(data))

    def pong(self, data=b''):
        if data is not None:
            data = prepare_data(data)
        self.request.sendall(self._get_send_msg(data, op_code=OP_PONG))


class ZwebsocketApp(object):
    def __init__(self):
        self.pre_handle_urls = defaultdict()
        self.urls = defaultdict()
        self.after_handle_urls = defaultdict()

    def route(self, rule):
        def decorator(f):
            @functools.wraps(f)
            def inner(*args, **kwargs):
                res = f(*args, **kwargs)
                websocket = kwargs.get("websocket")
                if websocket:
                    websocket.finish()
                return res

            self.urls[rule] = inner
            return inner

        return decorator

    def before_route(self, rule):
        def decorator(f):
            self.pre_handle_urls[rule] = f
            return f

        return decorator

    def after_route(self, rule):
        def decorator(f):
            self.after_handle_urls[rule] = f
            return f

        return decorator

    def run(self, host="0.0.0.0", port=9999, multi_thread=True):
        """
        use exec function to create new class.
        Because of the socketServer need to provide a class type parameter,
        so the route can only define in the class variable. For this reason,
        when user use app.run by multi_thread, I dynamically create a new class by type function,
        so can prevent route overlap.
        :param host:
        :param port:
        :param multi_thread: If False, user must handle client msg on his own.
        :return:
        """
        logger.info(str(threading.current_thread()) + "websocket server at：" + host + ":" + str(port))
        new_class_name = "Zwebsocket_" + str(threading.current_thread().name).replace("-", "_")
        exec(new_class_name + " = type(\"{}\", (Zwebsocket, ), dict())".format(new_class_name))
        exec("{}.urls = self.urls".format(new_class_name))
        exec("{}.pre_handle_urls = self.pre_handle_urls".format(new_class_name))
        exec("{}.after_handle_urls = self.after_handle_urls".format(new_class_name))
        if not multi_thread:
            exec("{}.multi_thread={}".format(new_class_name, multi_thread))
        server = socketserver.ThreadingTCPServer((host, port), locals()[new_class_name])
        server.serve_forever()



if __name__ == "__main__":
    app1 = ZwebsocketApp()


    @app1.route('/log')
    @app1.auto_finish()
    def test(websocket, data):
        websocket.send_msg("回复消息：" + data)


    app2 = ZwebsocketApp()


    @app2.route('/log2')
    @app2.auto_finish()
    def test(websocket, data):
        websocket.send_msg("回复消息：" + data)
