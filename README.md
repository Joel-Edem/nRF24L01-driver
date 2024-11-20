# Simple nRF24L01 Driver

This is a simple and comple driver for the popular nRF24L01 module, written in micropython.
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
    radio = RadioDriver(CONFIG, IS_MASTER)
    radio.configure()
    
    out_buf = bytearray(CONFIG['DEFAULT_PL_SZ']) 
    in_buf = bytearray(CONFIG['DEFAULT_PL_SZ'])

    pkt_id = 0

    while True:
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

        await uasyncio.sleep_ms(0 if not IS_MASTER else 1000) 
        # you don't need to sleep.this is just to slow down ouptut. you can call sleep(0) to go as fast as possible

```

## Usage
A simple demonstration using the Enhanced ShockBurst™ protocol
- First You need to create a `config` object 
```python
PIPE = b"\xe1\xf0\xf0\xf0\xf0"
CONFIG = {
    "SPI_ID": 1,
    "SPI_MISO": 12,
    "SPI_MOSI": 11,
    "SPI_SCK": 10,
    "SPI_CSN": 13,
    "SPI_CE": 14,
    "TX_PIPE": PIPE,
    "RX_PIPE": PIPE,
    "CHANNEL": 97,
    "EN_DYNAMIC_PL": False,
    "DEFAULT_PL_SZ": 32,
    "NUM_RETRIES": 4,
    "RETRY_DELAY_US": 1000,  # NOTE: min=250, inreaments of 250 up to 250us*15
    "DATA_RATE": 1,  # NOTE: '00’ – 1Mbps ‘01’ – 2Mbps ‘02’ – 250kbps !shockburst is not available for 250kbs data rate
    "RF_POWER": 3,  # NOTE: (0)-18dBm  (1)-12dBm (2)-6dBm  (3)0dBm,

}
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
The status reutrned is an `int`. Status is positive if the data is sent successfully
and `0` if send fails. 

If the receiver receives the message and sends back a response, the value of status is `1`

If the receiver acknoledges the message without seding a response payload, the value of status is `2`

- You can check the status of the respose using like so using the `ResponseStatus` defined on the radio.
```python
res = await radio.exchange(out_buf, in_buf)
if res == radio.ResponseStatus.MSG_RECV:
    print("Message sent. Received response")
elif res == radio.ResponseStatus.MSG_SENT_NO_RESP:
    print("Message sent. Did not receive response")
elif res == radio.ResponseStatus.SEND_FAIL:
    print("Failed to send messsage")
```
- If you do not care about the response, a simple if check can be used since success states return possitive values.
```python
    if await radio.exchange(out_buf, in_buf):
        print("Message Sent")
    else:
        print("Send Failed")
```

> [!NOTE]
> Full refrence for all available fuctions can be found in the souce code in the doc strings.