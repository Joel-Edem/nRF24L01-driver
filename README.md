# Shockburst nRF24L01 Driver

This is a simple and compile driver for the popular nRF24L01 module, written in micropython.
This driver implements all necessary functions to easily access all registers,
allowing flexibility in configuration and protocol implementation. 
This driver also provides an implementation of the Enhanced ShockBurst™ protocol.

<p align="center">
  <img src="https://lastminuteengineers.com/wp-content/uploads/arduino/Pinout-nRF24L01-PA-LNA-External-Antenna-Wireless-Transceiver-Module.png"/>
</p>


## Demo
you can run the same code on the both devices.
```python
from nRF24L01 import RadioDriver
import uasyncio

CONFIG = ...
IS_MASTER = True # ISSUE FALSE ON OTHER DEVICE

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


        await uasyncio.sleep_ms(0 if not IS_MASTER else 1000) 
        # you don't need to sleep.this is just to slow down output. you can call sleep(0) to go as fast as possible

```

## Usage
A simple demonstration using the Enhanced ShockBurst™ protocol
- First You need to create a `config` object 
```python
IS_MASTER = True 
PIPE = b"\xe1\xf0\xf0\xf0\xf0"
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
    retry_delay_us=RETRY_DELAY_US,  # NOTE: min=250, increments of 250 up to 250us*15
    data_rate=DATA_RATE, # NOTE: '00’ – 1Mbps ‘01’ – 2Mbps ‘02’ – 250kbps !shockburst is not available for 250kbs data rate
    rf_power=RF_POWER # NOTE: (0)-18dBm  (1)-12dBm (2)-6dBm  (3)0dBm,

)

```
> NOTE: `CHANNEL`, `TX_PIPE` and `RX_PIPE` must be the same on both devices.
- Create and configure radio object.
```python
radio = RadioDriver(CONFIG, IS_MASTER)
radio.configure()
```
- Exchange Message. Exchange can be called from both devices.
```python
status = await radio.exchange(out_buf, in_buf)
```
### Response
The `exchange` method will send the buffer receiver and return a status. 
The status returned is an `int`. Status is positive if the data is sent successfully
and `0` if send fails. 

If the receiver receives the message and sends back a response, the value of status is `1`

If the receiver acknowledges the message without sending a response payload, the value of status is `2`

- You can check the status of the response using like so using the `ResponseStatus` defined on the radio.
```python
res = await radio.exchange(out_buf, in_buf)
if res == radio.ResponseStatus.MSG_RECV:
    print("Message sent. Received response")
elif res == radio.ResponseStatus.MSG_SENT_NO_RESP:
    print("Message sent. Did not receive response")
elif res == radio.ResponseStatus.SEND_FAIL:
    print("Failed to send message")
```
- If you do not care about the response, a simple if check can be used since success states return positive values.
```python
    if await radio.exchange(out_buf, in_buf):
        print("Message Sent")
    else:
        print("Send Failed")
```

## Demo 2
```python
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
        
        # you could check the status of a pending message status like so 
        # status = radio.check_msg_sent()
        # if status == radio.ResponseStatus.MSG_SENT:
        #     print("Msg Sent")
        # elif status == radio.ResponseStatus.MSG_SENT_NO_RESP:
        #     print("Msg Sent. Did not get response")
        # elif status == radio.ResponseStatus.SEND_FAIL:
        #     print("Could not send message")
            
        while radio.any():
            radio.readinto(in_buf)
            print(f"Received Response: {in_buf.decode()}")
        await uasyncio.sleep_ms(100)
```

> [!NOTE]
> Full reference for all available functions can be found in the source code in the doc strings.