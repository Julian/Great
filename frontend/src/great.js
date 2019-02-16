import axios from 'axios';

export default class Client {
  constructor(baseURL = '/api/music') {
    this.baseURL = baseURL;
  }
  async track() {
    const response = await axios.put(`${this.baseURL}/artists/tracked`);
    return response.data;
  }
  async tracked() {
    const response = await axios.get(`${this.baseURL}/artists/tracked`);
    return response.data;
  }
  library() {
    /* eslint class-methods-use-this: "off" */
    return [
      { name: 'Something', artist: { name: 'Someone' }, rating: 5 },
      { name: 'Another Thing', artist: { name: 'Same One' }, rating: 3 },
      {
        name: 'A Third Thing',
        artist: { name: 'A Different One' },
        rating: 5,
      },
    ];
  }
  radar() {
    /* eslint class-methods-use-this: "off" */
    return [
      { name: 'Something', artist: { name: 'Someone' } },
      { name: 'Another Thing', artist: { name: 'Same One' } },
      { name: 'A Third Thing', artist: { name: 'A Different One' } },
    ];
  }
}
