# Author: Joel Ametepeh
# Date: 2024-11-20
# Description: Driver for nRF240L01 transceiver.
#              This driver implements all registers as well as the Enhanced ShockBurst™ protocol.
#
# Copyright 2024 Joel Ametepeh <JoelAmetepeh@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NON-INFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import uasyncio
import utime
from machine import SPI, Pin
from micropython import const

_PIPES = (b"\xe1\xf0\xf0\xf0\xf0", b"\xd2\xf0\xf0\xf0\xf0")
_RF_CHANNEL = 97
_DEFAULT_PAYLOAD_SZ = 16
_EN_DYNAMIC_PL = False
_NUM_RETRIES = 4
_RETRY_DELAY_US = 1000  # NOTE: min=250, increments of 250 up to 250us*15
_DATA_RATE = 1  # NOTE: '00’ – 1Mbps ‘01’ – 2Mbps ‘02’ – 250kbps # shockburst is not available for 250kbs data rate
_RF_POWER = 3  # NOTE: (0)-18dBm  (1)-12dBm (2)-6dBm  (3)0dBm


class NRF240LConfig:

    def __init__(self,
                 spi_id: int, spi_miso: int, spi_mosi: int, spi_sck: int, spi_csn: int, spi_ce: int,
                 tx_pipe: bytes = _PIPES[0],
                 rx_pipe: bytes = _PIPES[0],
                 channel: int = _RF_CHANNEL,
                 en_dynamic_pl: bool = _EN_DYNAMIC_PL,
                 default_pl_sz: int = _DEFAULT_PAYLOAD_SZ,
                 num_retries: int = _NUM_RETRIES,
                 retry_delay_us: int = _RETRY_DELAY_US,
                 data_rate: int = _DATA_RATE,
                 rf_power: int = _RF_POWER,
                 ):
        self.SPI_ID = spi_id
        self.SPI_MISO = spi_miso
        self.SPI_MOSI = spi_mosi
        self.SPI_SCK = spi_sck
        self.SPI_CSN = spi_csn
        self.SPI_CE = spi_ce
        self.TX_PIPE = tx_pipe
        self.RX_PIPE = rx_pipe
        self.CHANNEL = channel
        self.EN_DYNAMIC_PL = en_dynamic_pl
        self.DEFAULT_PL_SZ = default_pl_sz
        self.NUM_RETRIES = num_retries
        self.RETRY_DELAY_US = retry_delay_us
        self.DATA_RATE = data_rate
        self.RF_POWER = rf_power


class RadioDriver:
    CONFIG_REG = const(0X00)
    EN_AA_REG = const(0x01)
    EN_RXADDR_REG = const(0x02)
    SETUP_AW_REG = const(0x03)
    SETUP_RETR_REG = const(0x04)
    RF_CH_REG = const(0x05)
    RF_SETUP_REG = const(0x06)
    STATUS_REG = const(0x07)
    OBSERVE_TX_REG = const(0x08)
    TX_ADDR_REG = const(0x10)
    RX_PW_P0_REG = const(0x11)
    RX_ADDR_REG = const(0x0A)
    DYNPD_REG = const(0x1C)
    FEATURE_REG = const(0X1D)
    FIFO_STATUS_REG = const(0x17)

    class ResponseStatus:
        SEND_FAIL = 0
        MSG_RECV = 1
        MSG_SENT_NO_RESP = 2
        MSG_PENDING = 3
        MSG_SENT = 4
        TIMED_OUT = 5
        FIFO_FULL = 6

    def __init__(self, config: NRF240LConfig, is_master):

        self.config = config
        self.is_master = is_master

        # initialize SPI
        self.spi: SPI | None = None
        self.csn = Pin(config.SPI_CSN, mode=Pin.OUT, value=1)
        self.ce = Pin(config.SPI_CE, mode=Pin.OUT, value=0)
        self._on = False
        self._reg_buf = memoryview(bytearray(1))
        self._dynamic_mode = config.DEFAULT_PL_SZ
        self._last_pl_sz = 0
        self.power_on()

    def power_on(self):
        if self.is_on:
            return
        print("nRF24L01 powering up")
        self.spi = SPI(self.config.SPI_ID, sck=Pin(self.config.SPI_SCK), mosi=Pin(self.config.SPI_MOSI),
                       miso=Pin(self.config.SPI_MISO))
        self.csn = Pin(self.config.SPI_CSN, mode=Pin.OUT, value=1)
        self.ce = Pin(self.config.SPI_CE, mode=Pin.OUT, value=0)
        utime.sleep_ms(100)
        if not self.check_device_responsive():
            print("Could Not start NRF Radio. Device is not responsive...")
            self._on = False
            return False

        self.toggle_power_up(True)  # set power up false
        self.ce(1)
        utime.sleep_us(10)
        self.ce(0)
        self._last_pl_sz = 0
        self._on = True
        print("nRF24L01 powered up")
        return True

    def power_off(self):
        if not self.is_on:
            return
        print("nRF24L01 powering down")
        self.toggle_power_up(False)
        self.ce(1)
        utime.sleep_us(10)
        self.ce(0)
        self.flush_tx_fifo()
        self.flush_rx_fifo()
        self.clear_status_flags()
        self.spi.deinit()
        self.csn(1)
        self._on = False
        self._last_pl_sz = 0
        print("nRF24L01 powered down")

    @property
    def is_on(self):
        return self._on

    def read_register(self, reg) -> memoryview:
        self.csn(0)
        self.spi.readinto(self._reg_buf, reg)
        self.spi.readinto(self._reg_buf)
        self.csn(1)
        return self._reg_buf

    def write_register(self, reg, value):
        # _WRITE_REG = 0x20
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0x20 | reg)
        if isinstance(value, int):
            self.spi.readinto(self._reg_buf, value)
        else:
            self.spi.write(value)
        self.csn(1)

    def toggle_register_bit(self, reg, bit_no, set_high):
        cur = self.read_register(reg)
        is_high = (cur[0] & (1 << bit_no)) != 0  # check if bit is high

        if not is_high and set_high:  # enable
            self.write_register(reg, cur[0] | (1 << bit_no))

        elif is_high and not set_high:  # disable
            self.write_register(reg, cur[0] & ~(1 << bit_no))
        return is_high

    def read_status_register(self) -> memoryview:
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0xFF)
        self.csn(1)
        return self._reg_buf

    def read_rx_payload(self, buf):
        """
        Read RX-payload: 1 – 32 bytes.
        Payload is deleted from FIFO after it is read
        :return:
        """
        # _R_RX_PAYLOAD = 0x61
        # get the data
        self._reg_buf[0] = 0xFF
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0x61)  # write cmd # ignore status
        self.spi.readinto(buf)
        self.csn(1)
        if self._reg_buf[0] == 0xFF:
            self._on = False
            raise OSError("FAILED TO Read RF PACKET Device not responsive")

    def tx_write_payload_ack(self, buf, send=True):
        """
        write packet to tx fifo from output buffer,
         buf length must be equal to payload size if dynamic
         payload size is disabled
         W_TX_PAYLOAD = 0xA0
        :return:
        """
        # send the data
        self._reg_buf[0] = 0xff
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0xA0)
        self.spi.write(buf)
        self.csn(1)
        if send:
            self.ce(1)
            utime.sleep_us(10)
            self.ce(0)
        if self._reg_buf[0] == 0xff:
            self._on = False
            raise OSError("FAILED TO SEND RF PACKET Device not responsive")

    def tx_write_payload_no_ack(self, buf, send=True):
        # _W_TX_PAYLOAD_NO_ACK = 0xB0
        # send the data
        self._reg_buf[0] = 0xff
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0xB0)
        self.spi.write(buf)
        self.csn(1)
        if send:
            self.ce(1)
            utime.sleep_us(10)
            self.ce(0)
        if self._reg_buf[0] == 0xff:
            self._on = False
            raise OSError("FAILED TO SEND RF PACKET Device not responsive")

    def rx_write_ack_payload(self, buf, pipe_no=0):
        """

        :param buf:
        :param pipe_no: 0-5
        :return:
        """
        # _W_ACK_PAYLOAD = 0xA8 | pipe_no
        self._reg_buf[0] = 0xff
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0xA8 | pipe_no)
        self.spi.write(buf)
        self.csn(1)
        if self._reg_buf[0] == 0xff:
            self._on = False
            raise OSError("FAILED TO SEND RF ACK PACKET Device not responsive")

    def read_rx_payload_length(self) -> int:
        # _R_RX_PL_WID = 0x30
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0x96)  # write cmd # ignore status
        res = self.spi.read(1)
        self.csn(1)
        return int(res)

    def reuse_tx_payload(self):
        # _REUSE_TX_PL = 0xE3
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0xE3)
        self.csn(1)

    def flush_tx_fifo(self):
        # _FLUSH_TX = const(0xE1)
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0xE1)
        self.csn(1)

    def flush_rx_fifo(self):
        # _FLUSH_RX = const(0xE2)
        self.csn(0)
        self.spi.readinto(self._reg_buf, 0xE2)
        self.csn(1)

    def tx_fifo_full_flag(self) -> bool:
        """
        Check if tx fifo is full
        :return:
        """
        is_full = (self.read_status_register()[0] & (0x1 << 0)) != 0
        return is_full

    def tx_fifo_full(self) -> bool:
        """
        TX FIFO full flag in FIFO_STATUS.
        FIFO_STATUS = 0x17
        :return: True if TX FIFO full
        """
        return self.read_register(self.FIFO_STATUS_REG)[0] & const(0x1 << 5) != 0

    def tx_fifo_empty(self) -> bool:
        """
        TX FIFO empty flag in FIFO_STATUS.
        :return: True if TX FIFO empty
        FIFO_STATUS = 0x17
        """

        return self.read_register(self.FIFO_STATUS_REG)[0] & 0x10 != 0

    def rx_fifo_full(self) -> bool:
        """
        TX FIFO full flag FIFO_STATUS.
        FIFO_STATUS = 0x17
        :return: True if TX FIFO full
        """

        return self.read_register(self.FIFO_STATUS_REG)[0] & const(0x1 << 1) != 0

    def get_rx_fifo_empty(self) -> bool:
        """
        RX FIFO empty flag FIFO_STATUS.
        _FIFO_STATUS = 0x17
        :return: True if RX FIFO empty
        """
        return self.read_register(self.FIFO_STATUS_REG)[0] & 0x1 != 0

    def enable_rx_irq(self, enable=True):
        """
        Enable interrupt caused by device when payload is received.
        It is set by toggling bit 7 in the `CONFIG` register LOW to ENABLE.
        :param enable: True or False
        :return:
        """
        # _CONFIG_REG = 0x00
        return self.toggle_register_bit(self.CONFIG_REG, 6, not enable)

    def enable_tx_irq(self, enable=True):
        """
        Enable interrupt caused by device when payload is transmitted.
        It is set by toggling bit 6 in the `CONFIG` register LOW to ENABLE.
        :param enable: True or False
        :return:
        """
        return self.toggle_register_bit(self.CONFIG_REG, 5, not enable)  # _CONFIG_REG

    def enable_max_retry_irq(self, enable=True):
        """
        Enable interrupt caused by device when maximum retries by tx fail.
        It is set by toggling bit 5 in the `CONFIG` register LOW to ENABLE.
        :param enable: True or False
        :return:
        """

        return self.toggle_register_bit(self.CONFIG_REG, 4, not enable)  # _CONFIG_REG

    def get_clear_rx_irq(self, clear=True) -> bool:
        """
        Check if the data received irq bit is set in the STATUS register.
        Write 1 to bit 7 to clear flag
        :param clear:
        :return:
        """

        cur = self.read_status_register()
        is_set = (cur[0] & 0x40) != 0
        if clear and is_set:
            self.write_register(self.STATUS_REG, cur[0] | 0x40)
        return is_set

    def get_clear_tx_irq(self, clear=True) -> bool:
        """
        Check if the data tx irq bit is set in the STATUS register.
        Write 1 to bit 6 to clear flag
        :param clear:
        :return:
        """
        cur = self.read_status_register()
        is_set = cur[0] & 0x20 != 0
        if clear and is_set:
            self.write_register(self.STATUS_REG, cur[0] | 0x20)
        return is_set

    def get_clear_max_rt_irq(self, clear=True) -> bool:
        """
        Check maximum number of TX retransmits irq is set in the STATUS register.
        Write 1 to bit position 5 to clear flag
        :param clear:
        :return:
        """
        cur = self.read_status_register()
        is_set = cur[0] & 0x10 != 0
        if clear and is_set:
            self.write_register(self.STATUS_REG, cur[0] | 0x10)
        return is_set

    def toggle_power_up(self, enable=True):
        """
        Put device in standby mode or active move
        It is set by toggling bit 2 in the `CONFIG` register
        1: POWER UP, 0:POWER DOWN
        :param enable: True or False
        :return:
        """
        return self.toggle_register_bit(self.CONFIG_REG, 1, enable)  # _CONFIG_REG

    def toggle_primary_rx(self, enable=True):
        """
        Put device in RX OR_TX_MODE
        It is set by toggling bit 1 in the `CONFIG` register
        1: PRX, 0: PTX
        :param enable: True or False
        :return:
        """
        return self.toggle_register_bit(self.CONFIG_REG, 0, enable)

    def set_data_rate(self, rate: int):
        """
        Select between the high speed data rates
        '00’ – 1Mbps ‘01’ – 2Mbps ‘2’ – 250kbps
        Configured using the RF_DR_LOW and RF_DR_HIGH bits in the RF_SETUP register.

        :param rate: 0-2
        :return:
        """
        assert 0 <= rate <= 2
        cur = self.read_register(self.RF_SETUP_REG)[0] & ~0x28  # 1Mbps
        if rate == 1:  # 2Mbps
            cur |= (0x1 << 3)
        elif rate == 2:  # 250kbps
            cur |= (0x1 << 5)
        self.write_register(self.RF_SETUP_REG, cur)

    def set_rf_power(self, power: int):
        """
        Set RF output power in TX mode
        (0)'00' – -18dBm
        (1)'01' – -12dBm
        (2)'10' – -6dBm
        (3)'11' – 0dBm
        :param power: 0-3
        :return:
        """
        assert 0 <= power <= 3
        self.write_register(self.RF_SETUP_REG, self.read_register(self.RF_SETUP_REG)[0] & ~0x06 | (power << 1))

    def en_crc(self, enable=True):
        """
        Toggle Crc. Forced High if Auto Ack is enabled.
        It is set by toggling bit 4 in the `CONFIG` register HIGH to ENABLE.
        :param enable: True or False
        :return:
        """
        return self.toggle_register_bit(self.CONFIG_REG, 3, enable)  # _CONFIG_REG

    def set_crc_scheme(self, length=1):
        """
        Set CRC encoding scheme.
        It is set by toggling bit no. 3
        '0' = 1 byte;    '1' = 2 bytes;
        :param length: 0 or 1
        :return:
        """
        return self.toggle_register_bit(self.CONFIG_REG, 2, length)  # _CONFIG_REG

    def set_auto_retry_delay(self, delay_lv: int):
        """
        Delay  from end of transmission to start of next retransmission.
        increases in 250us increments to a max of 4000us.
        set by bits 4-7 in the SETUP_RETR Register
        :param delay_lv:int values 0 - 15
        :return:
        """
        assert 0 <= delay_lv <= 15
        reg_val = self.read_register(self.SETUP_RETR_REG)
        cur = (reg_val[0] & 0xf0) >> 4
        self.write_register(self.SETUP_RETR_REG, (reg_val[0] & ~0xf0) | (delay_lv << 4))
        return cur

    def set_auto_retry_count(self, retries: int):
        """
        Sets number of retries to attempt before a transaction is aborted.
        the device can retry up to 15 times before aborting
        set in the SETUP_RETR Register
        :return:
        """
        assert 0 <= retries <= 15
        reg_val = self.read_register(self.SETUP_RETR_REG)
        cur = (reg_val[0] & 0x0f) >> 0
        self.write_register(self.SETUP_RETR_REG, (reg_val[0] & ~cur) | retries)

    def get_lost_packet_count(self) -> int:
        """
        Count lost packets.
        This counter is incremented when a packet fails be acknowledged and Max retries is reached.
        It counts the number of max retries that have occurred. this can help indicate channel quality.
        The counter is overflow protected to 15and discontinues at max until reset.
        The counter is reset by writing to RF_CH.
        _OBSERVE_TX = 0x08
        :return:
        """
        return (self.read_register(self.OBSERVE_TX_REG)[0] & 0xf0) >> 4

    def get_retry_attempts(self) -> int:
        """
        This counter is incremented if an ack packet is not received.
        Count retransmitted packets.
        The counter is reset when transmission of a new packet starts
        :return:
        """

        return (self.read_register(self.OBSERVE_TX_REG)[0] & 0x0f) >> 0

    def set_channel(self, channel: int):
        """
        Sets the frequency channel nRF24L01+ operates on.
        Set in the RF_CH register
        :param channel: 0-125
        :return:
        """
        assert 0 <= channel <= 125
        self.write_register(self.RF_CH_REG, channel)

    def set_address_width(self, length: int):
        """
        Setup of Address Widths (common for all data pipes).
        this is configured through the SETUP_AW register
        '00' - Illegal
        '01' - 3 bytes
        '10' - 4 bytes
        '11' – 5 bytes
        :param length: 3, 4, or 5
        :return:
        """
        assert 3 <= length <= 5
        self.write_register(self.SETUP_AW_REG, length - 2)

    def toggle_enable_rx_pipe(self, pipe_no: int = 0, enable: bool = True):
        """
        Enable rx data pipe.
        THis is done by setting the appropriate bit[0-5] in the EN_RXADDR[0x02] register
        _EN_RXADDR = 0x02
        :param enable:
        :param pipe_no: number between 0-5 inclusive
        :return:
        """
        assert 0 <= pipe_no <= 5
        return self.toggle_register_bit(self.EN_RXADDR_REG, pipe_no, enable)

    def set_rx_pipe_address(self, pipe_no, address):
        """
        Sets address for rx pipes. pipes 0 -1 can have unique 5 bit address.
        pipes 2-5 hare the top 4 bits with pipe 1. only LSB is set for these pipes.
        :param pipe_no:
        :param address:
        :return:
        """

        assert 0 <= pipe_no <= 5
        dest = self.RX_ADDR_REG + pipe_no
        if pipe_no >= 2:
            address = address[0]
        self.write_register(dest, address)

    def set_tx_pipe_address(self, address):
        """
        Set tx address Used for PTX.
        Transmit address. Used for a PTX device only. (LSByte is written first)
        Set RX_ADDR_P0 equal to this address to handle automatic acknowledge if
        this is a PTX device with Enhanced ShockBurstTM enabled.
        _TX_ADDR = 0x10
        :param address:
        :return:
        """
        assert len(address) == 5
        self.write_register(self.TX_ADDR_REG, address)

    def toggle_auto_ack_for_pipe(self, pipe_no: int = 0, enable: bool = True):
        """
        Enable auto acknowledgement data pipe.
        THis is done by setting the appropriate bit[0-5] in the EN_AA[0x01] register
        _EN_AA = 0x01
        :param enable: enable or disable pipe
        :param pipe_no: number between 0-5 inclusive
        :return:
        """

        assert 0 <= pipe_no <= 5
        return self.toggle_register_bit(self.EN_AA_REG, pipe_no, enable)

    def enable_dynamic_pyload_length_for_pipe(self, pipe_no, enable=True):
        """
        Enable dynamic payload length.
        DYNPD = 0x1C
        :param enable:
        :param pipe_no: 0-5
        :return:
        """

        assert 0 <= pipe_no <= 5
        return self.toggle_register_bit(self.DYNPD_REG, pipe_no, enable)

    def get_data_pipe_for_reading(self) -> int | None:
        """
        used to get the data pipe number for the payload available
        for reading from RX_FIFO
        :return: 0 - 5
        """
        val = (self.read_status_register()[0] & 0x0E) >> 1
        if val == 7 or val == 6:  # rx fifo empty
            return None
        return val

    def toggle_dynamic_payload_length_enabled(self, enable=True):
        """
        Enables Dynamic Payload Length Feature
         # _FEATURE = 0X1D
        :param enable:
        :return:
        """

        return self.toggle_register_bit(self.FEATURE_REG, 2, enable)

    def set_rx_payload_length(self, pipe_no, payload_length):
        """
        Set number of bytes in RX payload in data
        RX_PW_P0 = 0x11
        :param pipe_no: 0-5
        :param payload_length: 1-32 bytes
        :return:
        """

        assert 0 <= pipe_no <= 5
        assert 1 <= payload_length <= 32

        self.write_register(self.RX_PW_P0_REG + pipe_no, payload_length)

    def enable_payloads_with_ack(self, enable):
        """
        Enables Payload with ACK cmd
        FEATURE = 0X1D
        :param enable:
        :return:
        """
        return self.toggle_register_bit(self.FEATURE_REG, 1, enable)

    def enable_no_ack_cmd(self, enable):
        """
        Enables the W_TX_PAYLOAD_NOACK command
        :param enable:
        :return:
        """
        # _FEATURE = 0X1D
        return self.toggle_register_bit(self.FEATURE_REG, 0, enable)

    def clear_status_flags(self):
        """
        clears RX_DR |TX_DS |MAX_RT flags in STATUS REGISTER
        :return:
        """
        self.write_register(self.STATUS_REG, self.read_status_register()[0] | 0x10 | 0x20 | 0x40)

    def check_device_responsive(self) -> bool:
        """
        Checks if device is responsive to commands
        :return:
        """
        expect_true = self.toggle_power_up(False)
        expect_false = self.toggle_power_up(True)
        # self.toggle_power_up(expect_true)
        return expect_true != expect_false

    def _shockburst_config(self):

        # clear irq flags in status register
        self.clear_status_flags()
        # flush fifos
        self.flush_tx_fifo()
        self.flush_rx_fifo()
        # set power
        self.set_rf_power(self.config.RF_POWER)
        # set data rate
        self.set_data_rate(self.config.DATA_RATE)
        # enable crc
        self.en_crc()
        self.set_crc_scheme(1)
        # setup retries
        self.set_auto_retry_delay(int(self.config.RETRY_DELAY_US / 250))  # 4*250us = 1ms
        self.set_auto_retry_count(self.config.NUM_RETRIES)
        # Setup channels
        self.set_channel(self.config.CHANNEL)
        # set address width
        self.set_address_width(len(self.config.TX_PIPE))
        # enable pipe for shockburst
        self.toggle_enable_rx_pipe(0, True)
        # set pipe address
        self.set_rx_pipe_address(0, self.config.RX_PIPE)
        # enable auto ack for p0
        self.toggle_auto_ack_for_pipe(0)
        # Enable ack payloads
        self.enable_payloads_with_ack(True)
        if self.config.EN_DYNAMIC_PL:
            self.enable_dynamic_pyload_length_for_pipe(0, True)
            self.toggle_dynamic_payload_length_enabled()
        else:
            self.set_rx_payload_length(0, self.config.DEFAULT_PL_SZ)

    def configure_tx(self):
        if not self.is_on:
            print("Device is powered down")
            return False
        print("Configuring as PTX")
        # nRF24L01+ must be in a standby or power down mode before
        # writing to the configuration registers
        self.toggle_power_up(False)
        self._shockburst_config()
        # set as tx device
        self.toggle_primary_rx(False)
        # set tx address
        self.set_tx_pipe_address(self.config.TX_PIPE)
        print("nrf Configured as Primary TX (master)")
        # power up
        self.toggle_power_up(True)

    def configure_rx(self):
        if not self.is_on:
            print("Device is powered down")
            return False
        # nRF24L01+ must be in a standby or power down mode before writing to the configuration registers
        self.toggle_power_up(False)
        # do default config
        self._shockburst_config()
        # set as rx
        self.toggle_primary_rx(True)
        # power up
        self.toggle_power_up(True)

        self.ce(1)

    def configure(self):
        if not self.is_on:
            self.power_on()
        if self.is_master:
            self.configure_tx()
        else:
            self.configure_rx()

    async def master_exchange(self, out_buf, in_buf, ack_payload=True) -> int:
        """
        Send a message to prx and read response.
        If using dynamic payloads, you can check the size of the received response
        :param ack_payload: sets if the prx should send an ack packet
        :param out_buf: message to send
        :param in_buf: buffer to store response
        :return:
        """
        if not self.is_on:
            print("Device is powered down")
            return self.ResponseStatus.SEND_FAIL
        # TODO: if using dynamic payloads, can check the size of the
        #  received payload and incoming message prior to reading to
        #  prevent overflow in case of memory view objects.
        self.tx_write_payload_ack(out_buf) if ack_payload else self.tx_write_payload_no_ack(out_buf)
        # check for ack packet and check if ack contains response
        # await uasyncio.sleep_ms(0)  # about 130 us to transition to rx and back.
        self._last_pl_sz = 0
        while not self.get_clear_max_rt_irq(False):
            if self.get_clear_tx_irq(False):
                if self.get_clear_rx_irq(False):
                    # if self._dynamic_mode:
                    #     self._last_pl_sz = self.read_rx_payload_length()
                    self.read_rx_payload(in_buf)
                    self.clear_status_flags()
                    return self.ResponseStatus.MSG_RECV
                self.clear_status_flags()
                return self.ResponseStatus.MSG_SENT_NO_RESP
            await uasyncio.sleep_ms(0)

        self.clear_status_flags()
        self.flush_tx_fifo()
        return self.ResponseStatus.SEND_FAIL

    async def slave_exchange(self, out_buf, in_buf) -> int:
        if not self.is_on:
            print("Device is powered down")
            return self.ResponseStatus.SEND_FAIL
        self.rx_write_ack_payload(out_buf)
        while not self.get_clear_rx_irq(False):
            await uasyncio.sleep_ms(0)
        self.read_rx_payload(in_buf)
        # if self._dynamic_mode:
        #     self._last_pl_sz = self.read_rx_payload_length()
        self.clear_status_flags()
        return self.ResponseStatus.MSG_RECV

    async def exchange(self, out_buf, in_buf) -> int:
        if self.is_master:
            return await self.master_exchange(out_buf, in_buf)
        else:
            return await self.slave_exchange(out_buf, in_buf)

    async def slave_send(self, buf, timeout=-1) -> int:
        if not self.is_on:
            print("Device is powered down")
            return self.ResponseStatus.SEND_FAIL
        if self.tx_fifo_full_flag():
            if timeout == 0:
                await uasyncio.sleep_ms(0)
                return self.ResponseStatus.FIFO_FULL
            elif timeout < 0:
                while self.tx_fifo_full_flag():
                    await uasyncio.sleep_ms(0)
            else:
                t0 = utime.ticks_ms()
                while self.tx_fifo_full_flag():
                    await uasyncio.sleep_ms(0)
                    if utime.ticks_diff(utime.ticks_ms(), t0) > timeout:
                        return self.ResponseStatus.TIMED_OUT
        self.rx_write_ack_payload(buf)
        return self.ResponseStatus.MSG_PENDING

    async def master_send(self, buf, ack_pkt=True, retries=-1, timeout=-1) -> int:
        if not self._on:
            print("Device is powered down")
            return self.ResponseStatus.SEND_FAIL
        if self.tx_fifo_full_flag():
            if timeout == 0:
                if self.get_clear_max_rt_irq(False):
                    return self.ResponseStatus.SEND_FAIL
                return self.ResponseStatus.FIFO_FULL
            else:
                t0 = utime.ticks_ms()
                while self.tx_fifo_full_flag():
                    if self.get_clear_max_rt_irq():
                        self.ce(1)
                        utime.sleep_us(10)  # Todo: maybe sleep 0. but less than 4ms is not guaranteed in asyncio.
                        self.ce(0)
                        if self.tx_fifo_full_flag():
                            if not retries:
                                return self.ResponseStatus.SEND_FAIL
                            if 0 < timeout < utime.ticks_diff(utime.ticks_ms(), t0):
                                return self.ResponseStatus.TIMED_OUT
                            if retries > 0:
                                retries -= 1
                    await uasyncio.sleep_ms(0)
        while not self.tx_fifo_empty():
            self.ce(1)
            await uasyncio.sleep_ms(0)
            self.ce(0)
            if self.get_clear_max_rt_irq():
                break
        self.tx_write_payload_ack(buf) if ack_pkt else self.tx_write_payload_no_ack(buf)
        return self.ResponseStatus.MSG_PENDING

    async def send(self, buf, timeout=-1, retries=-1) -> int:
        if self.is_master:
            return await self.master_send(buf, timeout=timeout, retries=retries)
        else:
            return await self.slave_send(buf, timeout=timeout)

    def check_slave_msg_sent(self) -> int:
        if self.get_clear_tx_irq(True) or self.tx_fifo_empty():
            return self.ResponseStatus.MSG_SENT
        return self.ResponseStatus.MSG_PENDING

    def check_master_msg_sent(self) -> int:
        if self.get_clear_max_rt_irq(False):
            return self.ResponseStatus.SEND_FAIL
        if self.get_clear_tx_irq(True):
            return self.ResponseStatus.MSG_SENT
        if not self.tx_fifo_empty():
            return self.ResponseStatus.MSG_PENDING
        return self.ResponseStatus.SEND_FAIL

    async def clear_tx_buf(self, retry_first: bool = True):
        if retry_first:
            self.get_clear_max_rt_irq()
            self.ce(1)
            await uasyncio.sleep_ms(1)
            self.ce(0)
        self.flush_tx_fifo()
        self.get_clear_max_rt_irq()
        self.get_clear_tx_irq()

    def check_msg_sent(self) -> int:
        return self.check_master_msg_sent() if self.is_master else self.check_slave_msg_sent()

    def any(self) -> bool:
        return not self.get_rx_fifo_empty() or self.get_clear_rx_irq(False)

    def readinto(self, buf):
        self.read_rx_payload(buf)
        self.get_clear_rx_irq(True)
        return self.ResponseStatus.MSG_RECV
