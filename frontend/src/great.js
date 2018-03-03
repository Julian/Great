import axios from 'axios';

export default class Client {
  constructor(baseURL = '/api/music') {
    this.baseURL = baseURL;
  }
  async tracked() {
    const response = await axios.get(`${this.baseURL}/artists/tracked`);
    return response.data;
  }
}
