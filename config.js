const express = require('express');
const { exec } = require('child_process');
const axios = require('axios');
const app = express();
app.use(express.json());

const TELEGRAM_BOT_TOKEN = '7367888159:AAELMEXMwfLSyLF5nhWQNIHK2NRf775ySU4';
const TELEGRAM_API_URL = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}`;

app.post('/webhook', async (req, res) => {
  const message = req.body.message;

  if (message && message.text === '/run') {
    exec('bash setup.sh', (error, stdout, stderr) => {
      if (error) {
        console.error(`Error executing script: ${error}`);
        return sendMessage(message.chat.id, `Error: ${error.message}`);
      }
      sendMessage(message.chat.id, `Output: ${stdout}`);
    });
  } else {
    sendMessage(message.chat.id, 'Send /run to execute the shell script.');
  }

  res.sendStatus(200);
});

async function sendMessage(chatId, text) {
  try {
    await axios.post(`${TELEGRAM_API_URL}/sendMessage`, {
      chat_id: chatId,
      text: text,
    });
  } catch (error) {
    console.error(`Error sending message: ${error}`);
  }
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
