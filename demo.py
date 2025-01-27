import uasyncio

from nRF24L01 import RadioDriver

IS_MASTER = True 
PIPES = (b"\xe1\xf0\xf0\xf0\xf0", b"\xd2\xf0\xf0\xf0\xf0")
RF_CHANNEL = 97
DEFAULT_PAYLOAD_SZ = 16
EN_DYNAMIC_PL = False
NUM_RETRIES = 4
RETRIY_DELAY_US = 1000  # NOTE: min=250, inreaments of 250 up to 250us*15
DATA_RATE = 1  # NOTE: '00’ – 1Mbps ‘01’ – 2Mbps ‘02’ – 250kbps # shockburst is not available for 250kbs data rate
RF_POWER = 3  # NOTE: (0)-18dBm  (1)-12dBm (2)-6dBm  (3)0dBm
CONFIG = {
    "SPI_ID": 1,
    "SPI_MISO": 12,
    "SPI_MOSI": 11,
    "SPI_SCK": 10,
    "SPI_CSN": 13,
    "SPI_CE": 9,
    "TX_PIPE": PIPES[0],
    "RX_PIPE": PIPES[0],
    "CHANNEL": RF_CHANNEL,
    "EN_DYNAMIC_PL": EN_DYNAMIC_PL,
    "DEFAULT_PL_SZ": DEFAULT_PAYLOAD_SZ,
    "NUM_RETRIES": NUM_RETRIES,
    "RETRY_DELAY_US": RETRIY_DELAY_US,
    "DATA_RATE": DATA_RATE,
    "RF_POWER": RF_POWER,

}


async def demo():
    out_buf = bytearray(CONFIG['DEFAULT_PL_SZ'])
    in_buf = bytearray(CONFIG['DEFAULT_PL_SZ'])

    radio = RadioDriver(CONFIG, IS_MASTER)
    while not radio.check_device_responsive():
        await uasyncio.sleep_ms(1000)
    if not radio.check_device_responsive():
        raise Exception("ERROR: Could not start NRF Radio")
    radio.configure()

    pkt_id = 0

    while radio.is_on:
        msg = b'pkt id: %d' % pkt_id
        out_buf[:len(msg)] = msg
        print(f"Sending: {msg.decode()}")
        res = await radio.exchange(out_buf, in_buf)
        if res == radio.ResponseStatus.MSG_RECV:
            print(f"Received Response: {in_buf.decode()}")
            pkt_id += 1
        elif res == radio.ResponseStatus.MSG_SENT_NO_RESP:
            print("Did not receive response")
        else:
            print("Could not send message")

        await uasyncio.sleep_ms(1000)


if __name__ == "__main__":
    try:
        uasyncio.run(demo())
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        uasyncio.new_event_loop()
