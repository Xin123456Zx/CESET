import Axios from "axios"


const axios = Axios.create({
  baseURL: "/api",
  timeout: 10000000,
})

axios.interceptors.request.use(
  async (config: any) => {

    // config.headers["Access-Control-Allow-Origin"] = "*"
    config.headers["Accept"] = "application/json"
    // addPendingRequest(config)
    return config
  },
  function (error) {
    // Do something with request error
    return Promise.reject(error)
  }
)
axios.interceptors.response.use(
  async function (response) {
    if (response.data.code != 0) {

      return Promise.reject(response.data.message)
    }
    return response
  },
  function (error) {
    console.log("response===", error)

    return Promise.reject(error)
  }
)


interface RequsetOptions {
  data: Record<string, any>
  otherOptions: Record<string, any>
}
/**
 * api
 *
 * @export
 * @class Api
 * Static methods: get post put delete
 *
 * @url request path
 * @pkId primary key
 * @actions extra methods extended from the base url
 *
 */
/** 
 * actions example
{
    approval: {
        method: 'put', 
        url: 'approval/{id}'
    }
}
*/

type B = GetKey<RequsetOptions>

type Actions = {
  [key: string]: {
    url: string
    method: "post" | "get" | "delete" | "put"
  }
}

interface ApiOptions {
  url: string
  pkId?: string | undefined
  actions?: Actions
}

type OtherRequest =
  | { [key: keyof Actions]: ({ data, otherOptions }: Partial<RequsetOptions>) => void }
  | undefined

export default class Api<T extends Actions> implements ApiOptions {
  // [key: string]: any;
  url: string
  pkId?: string | undefined
  actions?: T
  content: OtherRequest
  constructor({ url, pkId, actions }: ApiOptions) {
    if (!/\/$/.test(url)) {
      url = url
    }
    this.url = url
    this.pkId = pkId
    this.actions = actions as T
    // Requests extended from the baseUrl
    if (actions) {
      // Object.keys(actions).forEach((key) => {
      //   this[key] = (data: any, otherOptions: any) => {
      //     const url = formatUrl(this.url + this.actions?.[key].url, data);
      //     return send(url, data, otherOptions, this.actions?.[key].method);
      //   };
      // });

      const data = Object.keys(actions).reduce<Exclude<OtherRequest, undefined>>(
        (result, current) => {
          result[current] = ({ data = {}, otherOptions = {} }: Partial<RequsetOptions>) => {
            const url = formatUrl(this.url + this.actions?.[current].url, data)
            return send(url, data, otherOptions, this.actions?.[current].method)
          }
          return result
        },
        {}
      )
      this.content = data
    }
  }

  /**
   *
   *
   * @param {*} data
   * @param {*} otherOptions
   * @return {*}
   * @memberof Api
   */
  get(data: any, otherOptions: any) {
      
    let url = `${this.url}{${this.pkId}}`
    url = formatUrl(url, data)
    return send(url, data, otherOptions)
  }
  query<T>({ data = {}, otherOptions = {} }: Partial<RequsetOptions>) {
    return send<T>(this.url, data, otherOptions)
  }
  create<T>({ data = {}, otherOptions = {} }: Partial<RequsetOptions>) {
    if(this.pkId){
      let url = `${this.url}{${this.pkId}}`
      url = formatUrl(url, data)
      return send<T>(url, data, otherOptions, "post")
    }else{
      return send<T>(this.url, data, otherOptions, "post")
    }

  }
  update(data: any, otherOptions: any) {
    let url = `${this.url}{${this.pkId}}`
    url = formatUrl(url, data)
    return send(url, data, otherOptions, "put")
  }
  delete(data: any, otherOptions: any) {
    let url = `${this.url}{${this.pkId}}`
    url = formatUrl(url, data)
    return send(url, data, otherOptions, "delete")
  }
  getNormal(data: any, otherOptions: any) {
    let url = `${this.url}`
    url = formatUrl(url, data)
    return send(url, data, otherOptions)
  }

  static get(url: any, data: any, otherOptions: any) {
    url = formatUrl(url, data)
    return send(url, data, otherOptions)
  }
  static post(url: any, data: any, otherOptions: any) {
    url = formatUrl(url, data)
    return send(url, data, otherOptions, "post")
  }
  static put(url: any, data: any, otherOptions: any) {
    url = formatUrl(url, data)
    return send(url, data, otherOptions, "put")
  }
  static delete(url: any, data: any, otherOptions: any) {
    url = formatUrl(url, data)
    return send(url, data, otherOptions, "delete")
  }
}
function send<T>(
  url: string,
  data: Record<string, any>,
  otherOptions: Record<string, any>,
  method = "get"
): Promise<BaseResponse<T>> {

  return new Promise((resolve, reject) => {
    let config = {}
    if (method == "get") {
      config = Object.assign({}, { url: url, method: method, params: data }, otherOptions)
    } else {
      if (
        otherOptions &&
        otherOptions.headers &&
        otherOptions.headers["Content-Type"] == "multipart/form-data"
      ) {
        fetch(import.meta.env.VITE_BASE_URL + url, {
          method: "post",
          headers: {

          },
          body: data.data
        })
          .then((res) => res.json())
          .then((res) => {
            resolve(res)
          })
          .catch((err) => {
    
            reject(err)
          })
        return
      }

      config = Object.assign({}, { url: url, method: method, data: data}, otherOptions)
    }
    axios
      .request(config)
      .then((res) => {
        console.log(res)
        let data = res.data
        if (data.size) {
          data = Object.assign({}, res.data, res)
        }

          resolve(data)

        
      })
      .catch((err) => {
        reject(err)
      })
  })
}

function isFormatUrl(url: string) {
  return url.indexOf("{") !== -1 && url.indexOf("}") !== -1
}

function formatUrl(url: string, dataModel: { [x: string]: any }, options = {}) {
  if (!options.hasOwnProperty("removeFormatModelProp")) {
    // By default, remove format properties from the dataModel that were already used in the url
    //@ts-ignore
    options.removeFormatModelProp = true
  }
  if (isFormatUrl(url)) {
    if (dataModel) {
      Object.keys(dataModel).forEach(function (key) {
        const varName = "{" + key + "}"
        if (url.indexOf(varName) !== -1) {
          url = url.replace(new RegExp(varName, "gm"), dataModel[key])
          // Whether to remove the corresponding property from the dataModel after formatting the url
          //@ts-ignore
          if (options.removeFormatModelProp) {
            delete dataModel[key]
          }
        }
      })
    } else {
      url.split("{").forEach(function (item) {
        if (item.indexOf("}") === item.length - 1) {
          url = url.replace("{" + item, "")
        }
      })
    }
    return url
  } else {
    return url
  }
}
