import sys

import uasyncio

from nRF24L01 import RadioDriver, NRF240LConfig

# noinspection PyProtectedMember,PyUnresolvedReferences
IS_MASTER = True if "Pico W" in sys.implementation._machine else False
print(IS_MASTER)
PIPES = (b"\xe1\xf0\xf0\xf0\xf0", b"\xd2\xf0\xf0\xf0\xf0")
RF_CHANNEL = 97
DEFAULT_PAYLOAD_SZ = 16
EN_DYNAMIC_PL = False
NUM_RETRIES = 4
RETRY_DELAY_US = 1000  # NOTE: min=250, increments of 250 up to 250us*15
DATA_RATE = 1  # NOTE: '00’ – 1Mbps ‘01’ – 2Mbps ‘02’ – 250kbps # shockburst is not available for 250kbs data rate
RF_POWER = 3  # NOTE: (0)-18dBm  (1)-12dBm (2)-6dBm  (3)0dBm

CONFIG = NRF240LConfig(
    spi_id=1,
    spi_miso=12,
    spi_mosi=11,
    spi_sck=10,
    spi_csn=13,
    spi_ce=9,
    tx_pipe=PIPES[0],
    rx_pipe=PIPES[0],
    channel=RF_CHANNEL,
    en_dynamic_pl=EN_DYNAMIC_PL,
    default_pl_sz=DEFAULT_PAYLOAD_SZ,
    num_retries=NUM_RETRIES,
    retry_delay_us=RETRY_DELAY_US,
    data_rate=DATA_RATE,
    rf_power=RF_POWER

)


async def async_demo():
    out_buf = bytearray(CONFIG.DEFAULT_PL_SZ)
    in_buf = bytearray(CONFIG.DEFAULT_PL_SZ)

    radio = RadioDriver(CONFIG, IS_MASTER)
    while not radio.check_device_responsive():
        await uasyncio.sleep_ms(1000)
    if not radio.check_device_responsive():
        raise Exception("ERROR: Could not start NRF Radio")
    radio.configure()

    pkt_id = 0
    try:
        while radio.is_on:
            msg = b'pkt id: %d' % pkt_id
            out_buf[:len(msg)] = msg
            print(f"Sending: {msg.decode()}")
            if IS_MASTER:
                res = await radio.send(out_buf, timeout=-1, retries=-1)
            else:
                res = await radio.send(out_buf, timeout=-1)

            if res == radio.ResponseStatus.MSG_PENDING:
                print("Msg Pending")
                pkt_id += 1
            elif res == radio.ResponseStatus.SEND_FAIL:
                print("send fail")
            elif res == radio.ResponseStatus.FIFO_FULL:
                print("fifo full")
            elif res == radio.ResponseStatus.TIMED_OUT:
                print("Timed out")
            else:
                print(f"Could not send msg: {res}")

            while radio.any():
                radio.readinto(in_buf)
                print(f"Received Response: {in_buf.decode()}")
            await uasyncio.sleep_ms(1000)
    finally:
        radio.power_off()


async def demo():
    out_buf = bytearray(CONFIG.DEFAULT_PL_SZ)
    in_buf = bytearray(CONFIG.DEFAULT_PL_SZ)

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
        uasyncio.run(async_demo())
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        uasyncio.new_event_loop()
