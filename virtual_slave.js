/**
 * ==============================================================================
 * 🏭 BTL MẠNG MÁY TÍNH - CHƯƠNG TRÌNH MÔ PHỎNG VIRTUAL MODBUS RTU SLAVE
 * ==============================================================================
 * Giả lập Vi điều khiển ESP8266 + Module Relay Modbus RTU + Cảm biến công nghiệp
 * Kết nối qua cặp cổng nối tiếp ảo: CNCB0 (Slave) <---> CNCA0 (Master Node-RED)
 * Tốc độ: 9600 bps | Data bits: 8 | Stop bits: 1 | Parity: None | Unit ID: 1
 *
 * CẢM BIẾN GIẢ LẬP:
 * - IN1 (Bit 0): Cảm biến tiệm cận từ LJ12A3 (Phát hiện phôi kim loại)
 * - IN2 (Bit 1): Cảm biến quang điện (Phát hiện phôi nói chung - kim loại & phi kim)
 *
 * CƠ CẤU CHẤP HÀNH:
 * - Coil 0: Động cơ DC kéo băng chuyền
 * - Coil 1: Solenoid 12V kết hợp đòn bẩy dẫn hướng gạt phôi kim loại
 * ==============================================================================
 */

const readline = require('readline');
let SerialPort;
try {
    SerialPort = require('C:/Users/Admin/.node-red/node_modules/serialport').SerialPort;
} catch (e) {
    try {
        SerialPort = require('serialport').SerialPort;
    } catch (e2) {
        console.error('Không tìm thấy thư viện serialport! Vui lòng kiểm tra môi trường Node.js.');
        process.exit(1);
    }
}

const PORT_NAME = 'CNCB0';
const BAUD_RATE = 9600;
const SLAVE_ID = 1;

// Trạng thái mô phỏng
let state = {
    connected: true,            // Trạng thái đường truyền (true = ONLINE, false = ĐỨT CÁP)
    conveyorRunning: false,     // Coil 0: Động cơ băng tải
    solenoidActive: false,      // Coil 1: Solenoid đòn bẩy gạt
    sensorMetal: false,         // IN1 (Bit 0): Cảm biến từ tiệm cận LJ12A3
    sensorOptical: false,       // IN2 (Bit 1): Cảm biến quang hiện diện phôi
    autoMode: true,             // Tự động sinh phôi khi băng tải chạy
    rxCount: 0,
    txCount: 0,
    crcErrors: 0,
    metalSpawned: 0,
    nonMetalSpawned: 0,
    metalSorted: 0
};

// Thuật toán kiểm lỗi CRC-16 Modbus RTU tiêu chuẩn (Poly: 0xA001)
function calcCRC(buf, len) {
    let crc = 0xFFFF;
    for (let pos = 0; pos < len; pos++) {
        crc ^= buf[pos];
        for (let i = 8; i !== 0; i--) {
            if ((crc & 1) !== 0) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

// Khởi tạo cổng nối tiếp
let port;
try {
    port = new SerialPort({
        path: PORT_NAME,
        baudRate: BAUD_RATE
    });
} catch (err) {
    console.error(`\x1b[31m[LỖI] Không thể mở cổng ${PORT_NAME}: ${err.message}\x1b[0m`);
    process.exit(1);
}

// Banner giao diện Terminal
function renderBanner() {
    console.clear();
    console.log('\x1b[36m╔═══════════════════════════════════════════════════════════════════════════╗\x1b[0m');
    console.log('\x1b[36m║   🏭  BTL MẠNG MÁY TÍNH - MÔ PHỎNG VIRTUAL MODBUS RTU SLAVE (ESP8266)     ║\x1b[0m');
    console.log('\x1b[36m║   Giám sát & Phân loại Phôi Kim loại Tự động qua SCADA Node-RED          ║\x1b[0m');
    console.log('\x1b[36m╚═══════════════════════════════════════════════════════════════════════════╝\x1b[0m');
    console.log(`\x1b[33m* Cổng Serial     :\x1b[0m \x1b[32m${PORT_NAME}\x1b[0m (Kết nối ảo với Master: \x1b[32mCNCA0\x1b[0m)`);
    console.log(`\x1b[33m* Thông số truyền :\x1b[0m 9600-8-N-1 | Modbus Slave Unit ID: \x1b[32m${SLAVE_ID}\x1b[0m`);
    console.log(`\x1b[33m* Cảm biến 2 kênh :\x1b[0m IN1 = Cảm biến từ LJ12A3 | IN2 = Cảm biến quang hiện diện`);
    console.log('\x1b[36m─────────────────────────────────────────────────────────────────────────────\x1b[0m');
    console.log('\x1b[35m[PHÍM ĐIỀU KHIỂN TƯƠNG TÁC TRỰC TIẾP]:\x1b[0m');
    console.log('  [\x1b[33mM\x1b[0m] Thả phôi KIM LOẠI      | [\x1b[33mP\x1b[0m] Thả phôi PHI KIM     | [\x1b[33mSPACE\x1b[0m] Bật/Tắt Auto');
    console.log('  [\x1b[33mS\x1b[0m] Bật/Dừng Băng chuyền   | [\x1b[33mD\x1b[0m] Giả lập ĐỨT CÁP      | [\x1b[33mC\x1b[0m] KẾT NỐI LẠI');
    console.log('  [\x1b[33mQ\x1b[0m] Thoát chương trình');
    console.log('\x1b[36m─────────────────────────────────────────────────────────────────────────────\x1b[0m\n');
}

// In dòng sự kiện
function logEvent(type, color, msg) {
    let now = new Date().toTimeString().split(' ')[0];
    let tag = `[${now}] [${type}]`;
    console.log(`${color}${tag.padEnd(20)}\x1b[0m ${msg}`);
}

// Cập nhật dòng trạng thái
setInterval(() => {
    let statusText = state.conveyorRunning ? '\x1b[32mBĂNG CHUYỀN CHẠY\x1b[0m' : '\x1b[31mBĂNG CHUYỀN DỪNG\x1b[0m';
    let connText = state.connected ? '\x1b[32mONLINE\x1b[0m' : '\x1b[31mOFFLINE (ĐỨT CÁP)\x1b[0m';
    let autoText = state.autoMode ? '\x1b[32mBẬT\x1b[0m' : '\x1b[33mTẮT\x1b[0m';
    let sensorText = state.sensorMetal ? '\x1b[33mKIM LOẠI\x1b[0m' : (state.sensorOptical ? '\x1b[35mPHI KIM\x1b[0m' : 'TRỐNG');
    let solText = state.solenoidActive ? '\x1b[36mĐÒN BẨY GẠT\x1b[0m' : 'CHỜ';

    readline.cursorTo(process.stdout, 0, 11);
    process.stdout.write(`\x1b[K📊 \x1b[1mTrạng thái:\x1b[0m Mạng: ${connText} | Băng tải: ${statusText} | Auto: ${autoText} | Cảm biến: ${sensorText} | Đòn bẩy: ${solText} | RX: \x1b[36m${state.rxCount}\x1b[0m | TX: \x1b[36m${state.txCount}\x1b[0m\n`);
}, 400);

// Xử lý gói tin nhận Modbus RTU
let rxBuffer = Buffer.alloc(0);

port.on('data', (chunk) => {
    if (!state.connected) {
        // Mô phỏng đứt cáp: Không phản hồi để kích hoạt Timeout 5s trên SCADA
        return;
    }

    rxBuffer = Buffer.concat([rxBuffer, chunk]);

    while (rxBuffer.length >= 8) {
        let slaveId = rxBuffer[0];
        let funcCode = rxBuffer[1];

        if (slaveId !== SLAVE_ID || ![1, 2, 3, 4, 5, 15, 16].includes(funcCode)) {
            rxBuffer = rxBuffer.slice(1);
            continue;
        }

        let frameLen = 8;
        if (funcCode === 15 || funcCode === 16) {
            let byteCount = rxBuffer[6];
            frameLen = 7 + byteCount + 2;
            if (rxBuffer.length < frameLen) break;
        }

        let receivedCrc = rxBuffer.readUInt16LE(frameLen - 2);
        let calculatedCrc = calcCRC(rxBuffer, frameLen - 2);

        if (receivedCrc !== calculatedCrc) {
            state.crcErrors++;
            rxBuffer = rxBuffer.slice(1);
            continue;
        }

        state.rxCount++;
        let frame = rxBuffer.slice(0, frameLen);
        rxBuffer = rxBuffer.slice(frameLen);

        processModbusRequest(frame);
    }
});

// Xử lý yêu cầu Modbus
function processModbusRequest(req) {
    let func = req[1];
    let addr = req.readUInt16BE(2);
    let valOrQty = req.readUInt16BE(4);

    let res = null;

    // 1. FC 02: Read Discrete Inputs (Đọc cảm biến IN1 và IN2)
    if (func === 2) {
        let byteCount = 1;
        let inputByte = (state.sensorMetal ? 0x01 : 0x00) | (state.sensorOptical ? 0x02 : 0x00);
        res = Buffer.from([SLAVE_ID, 0x02, byteCount, inputByte, 0x00, 0x00]);
        let crc = calcCRC(res, 4);
        res[4] = crc & 0xFF;
        res[5] = (crc >> 8) & 0xFF;
    }

    // 2. FC 01: Read Coils (Đọc Động cơ Coil 0 và Solenoid Coil 1)
    else if (func === 1) {
        let byteCount = 1;
        let coilByte = (state.conveyorRunning ? 1 : 0) | (state.solenoidActive ? 2 : 0);
        res = Buffer.from([SLAVE_ID, 0x01, byteCount, coilByte, 0x00, 0x00]);
        let crc = calcCRC(res, 4);
        res[4] = crc & 0xFF;
        res[5] = (crc >> 8) & 0xFF;
    }

    // 3. FC 05: Write Single Coil (Ghi lệnh điều khiển Coil)
    else if (func === 5) {
        let isTurnOn = (valOrQty === 0xFF00);

        if (addr === 0) {
            // Coil 0: Động cơ băng chuyền
            let changed = (state.conveyorRunning !== isTurnOn);
            state.conveyorRunning = isTurnOn;
            if (changed) {
                if (isTurnOn) {
                    logEvent('BĂNG TẢI', '\x1b[32m', 'Master gửi lệnh KHỞI ĐỘNG BĂNG CHUYỀN (Coil 0 = ON)');
                } else {
                    logEvent('BĂNG TẢI', '\x1b[31m', 'Master gửi lệnh DỪNG BĂNG CHUYỀN (Coil 0 = OFF)');
                }
            }
        } else if (addr === 1) {
            // Coil 1: Solenoid kích hoạt cơ cấu đòn bẩy gạt
            let changed = (state.solenoidActive !== isTurnOn);
            state.solenoidActive = isTurnOn;
            if (changed) {
                if (isTurnOn) {
                    state.metalSorted++;
                    logEvent('ĐÒN BẨY', '\x1b[36m', '⚡ Solenoid KÍCH HOẠT ĐÒN BẨY -> Gạt phôi kim loại vào khay chứa!');
                } else {
                    logEvent('ĐÒN BẨY', '\x1b[90m', '↩ Thu hồi Solenoid đòn bẩy về vị trí chờ (Coil 1 = OFF)');
                }
            }
        }

        // Echo response chuẩn FC05
        res = Buffer.from(req);
    }

    // 4. FC 0F: Write Multiple Coils
    else if (func === 15) {
        let qty = valOrQty;
        let coilByte = req[7];
        if (addr === 0 && qty >= 1) {
            state.conveyorRunning = Boolean(coilByte & 1);
        }
        if (qty >= 2) {
            state.solenoidActive = Boolean(coilByte & 2);
        }
        res = Buffer.from([SLAVE_ID, 0x0F, req[2], req[3], req[4], req[5], 0x00, 0x00]);
        let crc = calcCRC(res, 6);
        res[6] = crc & 0xFF;
        res[7] = (crc >> 8) & 0xFF;
    }

    if (res && state.connected) {
        port.write(res);
        state.txCount++;
    }
}

// Phôi kim loại đi qua: Kích hoạt cả IN1 (từ) và IN2 (quang)
function triggerMetalProduct() {
    if (!state.conveyorRunning) {
        logEvent('CẢNH BÁO', '\x1b[33m', 'Băng chuyền đang dừng! Phôi không thể di chuyển đến cảm biến.');
        return;
    }

    state.metalSpawned++;
    logEvent('PHÔI VÀO', '\x1b[33m', `📦 Phôi KIM LOẠI #${state.metalSpawned} vào băng chuyền -> Đang trôi tới cảm biến...`);

    setTimeout(() => {
        if (!state.conveyorRunning) return;
        state.sensorMetal = true;
        state.sensorOptical = true;
        logEvent('CẢM BIẾN', '\x1b[32m', '⚡ Cảm biến tiệm cận LJ12A3 (IN1) + Quang (IN2) PHÁT HIỆN KIM LOẠI (400ms)');

        setTimeout(() => {
            state.sensorMetal = false;
            state.sensorOptical = false;
        }, 400);
    }, 1200);
}

// Phôi phi kim đi qua: Chỉ kích hoạt IN2 (quang), IN1 giữ nguyên false
function triggerNonMetalProduct() {
    if (!state.conveyorRunning) {
        logEvent('CẢNH BÁO', '\x1b[33m', 'Băng chuyền đang dừng! Phôi không thể di chuyển.');
        return;
    }

    state.nonMetalSpawned++;
    logEvent('PHÔI VÀO', '\x1b[35m', `🪵 Phôi PHI KIM #${state.nonMetalSpawned} vào băng chuyền -> Đang trôi tới cảm biến...`);

    setTimeout(() => {
        if (!state.conveyorRunning) return;
        state.sensorOptical = true;
        logEvent('CẢM BIẾN', '\x1b[35m', '👁️ Cảm biến quang (IN2) kích hoạt | Cảm biến từ (IN1) KHÔNG kích hoạt -> Xác nhận PHI KIM');

        setTimeout(() => {
            state.sensorOptical = false;
        }, 400);
    }, 1200);
}

// Tự động sinh phôi khi băng tải chạy
setInterval(() => {
    if (state.autoMode && state.conveyorRunning && state.connected) {
        let isMetal = Math.random() < 0.65;
        if (isMetal) {
            triggerMetalProduct();
        } else {
            triggerNonMetalProduct();
        }
    }
}, 6500);

// Xử lý phím tương tác
readline.emitKeypressEvents(process.stdin);
if (process.stdin.isTTY) {
    process.stdin.setRawMode(true);
}

process.stdin.on('keypress', (str, key) => {
    if (key.ctrl && key.name === 'c' || key.name === 'q') {
        console.log('\n\x1b[31m[THOÁT] Đang đóng cổng kết nối và thoát chương trình mô phỏng...\x1b[0m');
        port.close(() => process.exit(0));
    }

    let k = (key.name || str || '').toLowerCase();

    if (k === 'm') {
        triggerMetalProduct();
    } else if (k === 'p') {
        triggerNonMetalProduct();
    } else if (k === 's') {
        state.conveyorRunning = !state.conveyorRunning;
        logEvent('THỦ CÔNG', '\x1b[36m', `Đổi trạng thái băng chuyền thủ công: ${state.conveyorRunning ? 'CHẠY' : 'DỪNG'}`);
    } else if (k === 'space') {
        state.autoMode = !state.autoMode;
        logEvent('CHẾ ĐỘ', '\x1b[35m', `Tự động sinh phôi: ${state.autoMode ? 'BẬT' : 'TẮT'}`);
    } else if (k === 'd') {
        state.connected = false;
        logEvent('MẠNG RS485', '\x1b[31m', '❌ GIẢ LẬP ĐỨT CÁP / MẤT TÍN HIỆU MODBUS (Không phản hồi Master để kích hoạt Timeout 5s)');
    } else if (k === 'c') {
        state.connected = true;
        logEvent('MẠNG RS485', '\x1b[32m', '✔️ ĐÃ KHÔI PHỤC KẾT NỐI MODBUS (Master sẽ phục hồi trạng thái ONLINE)');
    }
});

port.on('open', () => {
    renderBanner();
    logEvent('KHỞI ĐỘNG', '\x1b[32m', `Cổng ${PORT_NAME} đã mở thành công. Trạm Slave ID=${SLAVE_ID} sẵn sàng!`);
});

port.on('error', (err) => {
    logEvent('LỖI PORT', '\x1b[31m', err.message);
});
