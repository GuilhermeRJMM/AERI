// Gerado por tools/gerar-schemas-js.ps1 a partir de schemas/imoveis-urbanos-onr.schema.json.
// Nao editar a mao: altere o .json oficial e rode o script.
window.ONR_SCHEMA_URBANO = {
  "description": "Schema JSON para validação de arquivos de importação de imóveis urbanos para o ONR.",
  "type": "object",
  "properties": {
    "version": {
      "type": "string",
      "const": "1.2.0"
    },
    "cns": {
      "type": "string",
      "pattern": "^(?:\\d{6}|\\d{5}-\\d)$"
    },
    "imoveis": {
      "minItems": 1,
      "type": "array",
      "items": {
        "allOf": [
          {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "tipo_imovel": {
                    "type": "number",
                    "const": 1
                  },
                  "contexto_urbano": {
                    "anyOf": [
                      {
                        "type": "number",
                        "const": 1
                      },
                      {
                        "type": "number",
                        "const": 2
                      }
                    ]
                  },
                  "ato": {
                    "type": "number",
                    "const": 2
                  },
                  "tipo_matricula_transcricao": {
                    "type": "number",
                    "const": 1
                  },
                  "numero_matricula": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 10
                  },
                  "data_matricula": {
                    "anyOf": [
                      {
                        "type": "string",
                        "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "cnm": {
                    "anyOf": [
                      {
                        "type": "string",
                        "pattern": "^(?:\\d{6}\\.\\d\\.\\d{7}-\\d{2}|\\d{16})$"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "situacao": {
                    "anyOf": [
                      {
                        "type": "string"
                      },
                      {
                        "type": "number"
                      },
                      {
                        "type": "null",
                        "const": null
                      }
                    ]
                  },
                  "motivo_envio": {
                    "anyOf": [
                      {
                        "type": "number",
                        "const": 1
                      },
                      {
                        "type": "number",
                        "const": 2
                      }
                    ]
                  },
                  "georreferenciamento": {
                    "type": "boolean"
                  },
                  "protocolo_prenotacao": {
                    "anyOf": [
                      {
                        "type": "number",
                        "minimum": 1
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "data_protocolo_prenotacao": {
                    "anyOf": [
                      {
                        "type": "string",
                        "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "dados_imovel": {
                    "minItems": 1,
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "tipo_logradouro": {
                          "type": "number",
                          "minimum": 1,
                          "maximum": 311
                        },
                        "logradouro": {
                          "type": "string",
                          "maxLength": 150
                        },
                        "numero_logradouro": {
                          "type": "string",
                          "maxLength": 10
                        },
                        "complemento": {
                          "anyOf": [
                            {
                              "type": "string",
                              "maxLength": 100
                            },
                            {
                              "type": "null"
                            }
                          ]
                        },
                        "bairro": {
                          "anyOf": [
                            {
                              "type": "string",
                              "maxLength": 50
                            },
                            {
                              "type": "null"
                            }
                          ]
                        },
                        "cep": {
                          "type": "string",
                          "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                        },
                        "cod_ibge_municipio": {
                          "type": "number",
                          "minimum": 1000000,
                          "maximum": 9999999
                        },
                        "uf": {
                          "type": "number",
                          "minimum": 11,
                          "maximum": 53
                        },
                        "area_m2": {
                          "anyOf": [
                            {
                              "type": "number",
                              "minimum": 0
                            },
                            {
                              "type": "null"
                            }
                          ]
                        }
                      },
                      "required": [
                        "tipo_logradouro",
                        "logradouro",
                        "numero_logradouro",
                        "cep",
                        "cod_ibge_municipio",
                        "uf"
                      ],
                      "additionalProperties": false
                    }
                  },
                  "dados_pessoa": {
                    "anyOf": [
                      {
                        "type": "array",
                        "items": {
                          "allOf": [
                            {
                              "type": "object",
                              "properties": {
                                "nome_completo": {
                                  "type": "string",
                                  "maxLength": 150
                                },
                                "estrangeiro": {
                                  "type": "boolean"
                                },
                                "cpf_cnpj": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "pattern": "^(?:\\d{11}|\\d{14}|[A-Za-z0-9]{11}|[A-Za-z0-9]{14}|\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}|\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}-\\d{2}|[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}-[A-Za-z0-9]{2}|[A-Za-z0-9]{2}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\/[A-Za-z0-9]{4}-[A-Za-z0-9]{2})$"
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "nacionalidade": {
                                  "anyOf": [
                                    {
                                      "type": "number"
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "estado_civil": {
                                  "anyOf": [
                                    {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "const": 1
                                        },
                                        {
                                          "type": "number",
                                          "const": 2
                                        },
                                        {
                                          "type": "number",
                                          "const": 3
                                        },
                                        {
                                          "type": "number",
                                          "const": 4
                                        },
                                        {
                                          "type": "number",
                                          "const": 5
                                        },
                                        {
                                          "type": "number",
                                          "const": 6
                                        },
                                        {
                                          "type": "number",
                                          "const": 7
                                        }
                                      ]
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "regime_bens": {
                                  "anyOf": [
                                    {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "const": 1
                                        },
                                        {
                                          "type": "number",
                                          "const": 2
                                        },
                                        {
                                          "type": "number",
                                          "const": 3
                                        },
                                        {
                                          "type": "number",
                                          "const": 4
                                        },
                                        {
                                          "type": "number",
                                          "const": 5
                                        },
                                        {
                                          "type": "number",
                                          "const": 6
                                        },
                                        {
                                          "type": "number",
                                          "const": 7
                                        }
                                      ]
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "relacao_juridica": {
                                  "anyOf": [
                                    {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "const": 1
                                        },
                                        {
                                          "type": "number",
                                          "const": 2
                                        },
                                        {
                                          "type": "number",
                                          "const": 3
                                        },
                                        {
                                          "type": "number",
                                          "const": 4
                                        },
                                        {
                                          "type": "number",
                                          "const": 5
                                        },
                                        {
                                          "type": "number",
                                          "const": 6
                                        },
                                        {
                                          "type": "number",
                                          "const": 7
                                        },
                                        {
                                          "type": "number",
                                          "const": 8
                                        },
                                        {
                                          "type": "number",
                                          "const": 9
                                        },
                                        {
                                          "type": "number",
                                          "const": 10
                                        },
                                        {
                                          "type": "number",
                                          "const": 11
                                        },
                                        {
                                          "type": "number",
                                          "const": 12
                                        },
                                        {
                                          "type": "number",
                                          "const": 13
                                        },
                                        {
                                          "type": "number",
                                          "const": 14
                                        },
                                        {
                                          "type": "number",
                                          "const": 15
                                        },
                                        {
                                          "type": "number",
                                          "const": 16
                                        },
                                        {
                                          "type": "number",
                                          "const": 17
                                        },
                                        {
                                          "type": "number",
                                          "const": 18
                                        }
                                      ]
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "data_inicio_rel_juridica": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "data_fim_rel_juridica": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "percentual": {
                                  "anyOf": [
                                    {
                                      "type": "number",
                                      "minimum": 0,
                                      "maximum": 100
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "tipo_logradouro": {
                                  "anyOf": [
                                    {
                                      "type": "number",
                                      "minimum": 1,
                                      "maximum": 311
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "logradouro": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 150
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "numero_logradouro": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 10
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "complemento": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 100
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "bairro": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 50
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "cep": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "cod_ibge_municipio": {
                                  "anyOf": [
                                    {
                                      "type": "number"
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "uf": {
                                  "anyOf": [
                                    {
                                      "type": "number"
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                },
                                "condicao_parte": {
                                  "anyOf": [
                                    {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "const": 1
                                        },
                                        {
                                          "type": "number",
                                          "const": 2
                                        }
                                      ]
                                    },
                                    {
                                      "type": "null"
                                    }
                                  ]
                                }
                              },
                              "required": [
                                "estrangeiro",
                                "estado_civil"
                              ],
                              "additionalProperties": false
                            },
                            {
                              "anyOf": [
                                {
                                  "type": "object",
                                  "properties": {
                                    "relacao_juridica": {
                                      "type": "null"
                                    }
                                  },
                                  "additionalProperties": {}
                                },
                                {
                                  "type": "object",
                                  "properties": {
                                    "relacao_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "const": 1
                                        },
                                        {
                                          "type": "number",
                                          "const": 2
                                        },
                                        {
                                          "type": "number",
                                          "const": 3
                                        },
                                        {
                                          "type": "number",
                                          "const": 4
                                        },
                                        {
                                          "type": "number",
                                          "const": 5
                                        },
                                        {
                                          "type": "number",
                                          "const": 6
                                        },
                                        {
                                          "type": "number",
                                          "const": 7
                                        },
                                        {
                                          "type": "number",
                                          "const": 8
                                        },
                                        {
                                          "type": "number",
                                          "const": 9
                                        },
                                        {
                                          "type": "number",
                                          "const": 10
                                        },
                                        {
                                          "type": "number",
                                          "const": 11
                                        },
                                        {
                                          "type": "number",
                                          "const": 12
                                        },
                                        {
                                          "type": "number",
                                          "const": 13
                                        },
                                        {
                                          "type": "number",
                                          "const": 14
                                        },
                                        {
                                          "type": "number",
                                          "const": 15
                                        },
                                        {
                                          "type": "number",
                                          "const": 16
                                        },
                                        {
                                          "type": "number",
                                          "const": 17
                                        },
                                        {
                                          "type": "number",
                                          "const": 18
                                        }
                                      ]
                                    },
                                    "data_inicio_rel_juridica": {
                                      "type": "string",
                                      "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                    }
                                  },
                                  "required": [
                                    "relacao_juridica",
                                    "data_inicio_rel_juridica"
                                  ],
                                  "additionalProperties": {}
                                }
                              ]
                            }
                          ]
                        }
                      },
                      {
                        "type": "null"
                      }
                    ]
                  },
                  "cib": {
                    "type": "string",
                    "pattern": "^(?:[A-Za-z0-9]{8}|[A-Za-z0-9]{7}-[A-Za-z0-9])$"
                  }
                },
                "required": [
                  "tipo_imovel",
                  "contexto_urbano",
                  "ato",
                  "tipo_matricula_transcricao",
                  "numero_matricula"
                ],
                "additionalProperties": {}
              },
              {
                "anyOf": [
                  {
                    "type": "object",
                    "properties": {
                      "motivo_envio": {
                        "anyOf": [
                          {
                            "type": "number",
                            "const": 1
                          },
                          {
                            "type": "number",
                            "const": 2
                          }
                        ]
                      },
                      "georreferenciamento": {
                        "type": "boolean"
                      },
                      "sistema_coordenadas": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "fuso_zona": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "sistema_referencia": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_poligono": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "coordenadas": {
                        "anyOf": [
                          {
                            "description": "Lista de coordenadas formatada como string (Geo/UTM/GMS) conforme Manual Unificado.",
                            "type": "string",
                            "maxLength": 3000
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "certificacao_incra": {
                        "type": "boolean"
                      },
                      "tipo_matricula_transcricao": {
                        "type": "number",
                        "const": 1
                      },
                      "protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "categoria_poligono": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "situacao": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "string",
                                "const": "1"
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "string",
                                "const": "2"
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "string",
                                "const": "3"
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "string",
                                "const": "4"
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "string",
                                "const": "5"
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "string",
                                "const": "6"
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "dados_confrontantes": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "type": "object",
                              "properties": {
                                "numero_matricula_confrontante": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 800
                                    },
                                    {
                                      "type": "number"
                                    }
                                  ]
                                },
                                "nome_proprietario_confrontante": {
                                  "type": "string",
                                  "maxLength": 800
                                }
                              },
                              "additionalProperties": false
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_ato": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_titularidade": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              },
                              {
                                "type": "number",
                                "const": 13
                              },
                              {
                                "type": "number",
                                "const": 14
                              },
                              {
                                "type": "number",
                                "const": 15
                              },
                              {
                                "type": "number",
                                "const": 16
                              },
                              {
                                "type": "number",
                                "const": 17
                              },
                              {
                                "type": "number",
                                "const": 18
                              },
                              {
                                "type": "number",
                                "const": 19
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_imovel": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_ato": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_imposto": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_transacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_imovel": {
                        "type": "number",
                        "const": 1
                      },
                      "contexto_urbano": {
                        "type": "number",
                        "const": 1
                      },
                      "dados_imovel": {
                        "minItems": 1,
                        "type": "array",
                        "items": {
                          "type": "object",
                          "properties": {
                            "tipo_logradouro": {
                              "type": "number",
                              "minimum": 1,
                              "maximum": 311
                            },
                            "logradouro": {
                              "type": "string",
                              "maxLength": 150
                            },
                            "numero_logradouro": {
                              "type": "string",
                              "maxLength": 10
                            },
                            "complemento": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 100
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "bairro": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 50
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "cep": {
                              "type": "string",
                              "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                            },
                            "cod_ibge_municipio": {
                              "type": "number",
                              "minimum": 1000000,
                              "maximum": 9999999
                            },
                            "uf": {
                              "type": "number",
                              "minimum": 11,
                              "maximum": 53
                            },
                            "area_m2": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "minimum": 0
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            }
                          },
                          "required": [
                            "tipo_logradouro",
                            "logradouro",
                            "numero_logradouro",
                            "cep",
                            "cod_ibge_municipio",
                            "uf"
                          ],
                          "additionalProperties": false
                        }
                      },
                      "dados_pessoa": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "allOf": [
                                {
                                  "type": "object",
                                  "properties": {
                                    "nome_completo": {
                                      "type": "string",
                                      "maxLength": 150
                                    },
                                    "estrangeiro": {
                                      "type": "boolean"
                                    },
                                    "cpf_cnpj": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{11}|\\d{14}|[A-Za-z0-9]{11}|[A-Za-z0-9]{14}|\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}|\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}-\\d{2}|[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}-[A-Za-z0-9]{2}|[A-Za-z0-9]{2}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\/[A-Za-z0-9]{4}-[A-Za-z0-9]{2})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "nacionalidade": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "estado_civil": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "regime_bens": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "relacao_juridica": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_inicio_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_fim_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "percentual": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 0,
                                          "maximum": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "tipo_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 1,
                                          "maximum": 311
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 150
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "numero_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 10
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "complemento": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "bairro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 50
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cep": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cod_ibge_municipio": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "uf": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "condicao_parte": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    }
                                  },
                                  "required": [
                                    "estrangeiro",
                                    "estado_civil"
                                  ],
                                  "additionalProperties": false
                                },
                                {
                                  "anyOf": [
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "type": "null"
                                        }
                                      },
                                      "additionalProperties": {}
                                    },
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        "data_inicio_rel_juridica": {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        }
                                      },
                                      "required": [
                                        "relacao_juridica",
                                        "data_inicio_rel_juridica"
                                      ],
                                      "additionalProperties": {}
                                    }
                                  ]
                                }
                              ]
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cif": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 25
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cib": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^(?:[A-Za-z0-9]{8}|[A-Za-z0-9]{7}-[A-Za-z0-9])$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "area_terreno_total": {
                        "anyOf": [
                          {
                            "type": "object",
                            "properties": {
                              "valor": {
                                "type": "number",
                                "minimum": 0
                              },
                              "unidade": {
                                "anyOf": [
                                  {
                                    "type": "number",
                                    "const": 1
                                  },
                                  {
                                    "type": "number",
                                    "const": 2
                                  }
                                ]
                              }
                            },
                            "required": [
                              "valor",
                              "unidade"
                            ],
                            "additionalProperties": false
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_matricula": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 10
                      },
                      "data_matricula": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "livro_matricula": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 5
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "folha_matricula": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 10
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cnm": {
                        "type": "string",
                        "pattern": "^(?:\\d{6}\\.\\d\\.\\d{7}-\\d{2}|\\d{16})$"
                      }
                    },
                    "required": [
                      "georreferenciamento",
                      "tipo_matricula_transcricao",
                      "tipo_imovel",
                      "contexto_urbano",
                      "numero_matricula",
                      "data_matricula",
                      "cnm"
                    ],
                    "additionalProperties": false
                  },
                  {
                    "type": "object",
                    "properties": {
                      "motivo_envio": {
                        "anyOf": [
                          {
                            "type": "number",
                            "const": 1
                          },
                          {
                            "type": "number",
                            "const": 2
                          }
                        ]
                      },
                      "georreferenciamento": {
                        "type": "boolean"
                      },
                      "sistema_coordenadas": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "fuso_zona": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "sistema_referencia": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_poligono": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "coordenadas": {
                        "anyOf": [
                          {
                            "description": "Lista de coordenadas formatada como string (Geo/UTM/GMS) conforme Manual Unificado.",
                            "type": "string",
                            "maxLength": 3000
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "certificacao_incra": {
                        "type": "boolean"
                      },
                      "tipo_matricula_transcricao": {
                        "type": "number",
                        "const": 2
                      },
                      "protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "categoria_poligono": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "situacao": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "string",
                                "const": "1"
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "string",
                                "const": "2"
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "string",
                                "const": "3"
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "string",
                                "const": "4"
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "string",
                                "const": "5"
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "string",
                                "const": "6"
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "dados_confrontantes": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "type": "object",
                              "properties": {
                                "numero_matricula_confrontante": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 800
                                    },
                                    {
                                      "type": "number"
                                    }
                                  ]
                                },
                                "nome_proprietario_confrontante": {
                                  "type": "string",
                                  "maxLength": 800
                                }
                              },
                              "additionalProperties": false
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_ato": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_titularidade": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              },
                              {
                                "type": "number",
                                "const": 13
                              },
                              {
                                "type": "number",
                                "const": 14
                              },
                              {
                                "type": "number",
                                "const": 15
                              },
                              {
                                "type": "number",
                                "const": 16
                              },
                              {
                                "type": "number",
                                "const": 17
                              },
                              {
                                "type": "number",
                                "const": 18
                              },
                              {
                                "type": "number",
                                "const": 19
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_imovel": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_ato": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_imposto": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_transacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_imovel": {
                        "type": "number",
                        "const": 1
                      },
                      "contexto_urbano": {
                        "type": "number",
                        "const": 1
                      },
                      "dados_imovel": {
                        "minItems": 1,
                        "type": "array",
                        "items": {
                          "type": "object",
                          "properties": {
                            "tipo_logradouro": {
                              "type": "number",
                              "minimum": 1,
                              "maximum": 311
                            },
                            "logradouro": {
                              "type": "string",
                              "maxLength": 150
                            },
                            "numero_logradouro": {
                              "type": "string",
                              "maxLength": 10
                            },
                            "complemento": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 100
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "bairro": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 50
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "cep": {
                              "type": "string",
                              "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                            },
                            "cod_ibge_municipio": {
                              "type": "number",
                              "minimum": 1000000,
                              "maximum": 9999999
                            },
                            "uf": {
                              "type": "number",
                              "minimum": 11,
                              "maximum": 53
                            },
                            "area_m2": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "minimum": 0
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            }
                          },
                          "required": [
                            "tipo_logradouro",
                            "logradouro",
                            "numero_logradouro",
                            "cep",
                            "cod_ibge_municipio",
                            "uf"
                          ],
                          "additionalProperties": false
                        }
                      },
                      "dados_pessoa": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "allOf": [
                                {
                                  "type": "object",
                                  "properties": {
                                    "nome_completo": {
                                      "type": "string",
                                      "maxLength": 150
                                    },
                                    "estrangeiro": {
                                      "type": "boolean"
                                    },
                                    "cpf_cnpj": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{11}|\\d{14}|[A-Za-z0-9]{11}|[A-Za-z0-9]{14}|\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}|\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}-\\d{2}|[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}-[A-Za-z0-9]{2}|[A-Za-z0-9]{2}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\/[A-Za-z0-9]{4}-[A-Za-z0-9]{2})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "nacionalidade": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "estado_civil": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "regime_bens": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "relacao_juridica": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_inicio_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_fim_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "percentual": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 0,
                                          "maximum": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "tipo_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 1,
                                          "maximum": 311
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 150
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "numero_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 10
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "complemento": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "bairro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 50
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cep": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cod_ibge_municipio": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "uf": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "condicao_parte": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    }
                                  },
                                  "required": [
                                    "estrangeiro",
                                    "estado_civil"
                                  ],
                                  "additionalProperties": false
                                },
                                {
                                  "anyOf": [
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "type": "null"
                                        }
                                      },
                                      "additionalProperties": {}
                                    },
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        "data_inicio_rel_juridica": {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        }
                                      },
                                      "required": [
                                        "relacao_juridica",
                                        "data_inicio_rel_juridica"
                                      ],
                                      "additionalProperties": {}
                                    }
                                  ]
                                }
                              ]
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cif": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 25
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cib": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^(?:[A-Za-z0-9]{8}|[A-Za-z0-9]{7}-[A-Za-z0-9])$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "area_terreno_total": {
                        "anyOf": [
                          {
                            "type": "object",
                            "properties": {
                              "valor": {
                                "type": "number",
                                "minimum": 0
                              },
                              "unidade": {
                                "anyOf": [
                                  {
                                    "type": "number",
                                    "const": 1
                                  },
                                  {
                                    "type": "number",
                                    "const": 2
                                  }
                                ]
                              }
                            },
                            "required": [
                              "valor",
                              "unidade"
                            ],
                            "additionalProperties": false
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_transcricao": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 10
                      },
                      "data_transcricao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "livro_transcricao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 5
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "folha_transcricao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 10
                          },
                          {
                            "type": "null"
                          }
                        ]
                      }
                    },
                    "required": [
                      "georreferenciamento",
                      "tipo_matricula_transcricao",
                      "tipo_imovel",
                      "contexto_urbano",
                      "numero_transcricao",
                      "data_transcricao"
                    ],
                    "additionalProperties": false
                  }
                ]
              },
              {
                "anyOf": [
                  {
                    "type": "object",
                    "properties": {
                      "motivo_envio": {
                        "anyOf": [
                          {
                            "type": "number",
                            "const": 1
                          },
                          {
                            "type": "number",
                            "const": 2
                          }
                        ]
                      },
                      "georreferenciamento": {
                        "type": "boolean"
                      },
                      "sistema_coordenadas": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "fuso_zona": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "sistema_referencia": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_poligono": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "coordenadas": {
                        "anyOf": [
                          {
                            "description": "Lista de coordenadas formatada como string (Geo/UTM/GMS) conforme Manual Unificado.",
                            "type": "string",
                            "maxLength": 3000
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "certificacao_incra": {
                        "type": "boolean"
                      },
                      "tipo_matricula_transcricao": {
                        "type": "number",
                        "const": 1
                      },
                      "protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "categoria_poligono": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "situacao": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "string",
                                "const": "1"
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "string",
                                "const": "2"
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "string",
                                "const": "3"
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "string",
                                "const": "4"
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "string",
                                "const": "5"
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "string",
                                "const": "6"
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "dados_confrontantes": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "type": "object",
                              "properties": {
                                "numero_matricula_confrontante": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 800
                                    },
                                    {
                                      "type": "number"
                                    }
                                  ]
                                },
                                "nome_proprietario_confrontante": {
                                  "type": "string",
                                  "maxLength": 800
                                }
                              },
                              "additionalProperties": false
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_ato": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_titularidade": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              },
                              {
                                "type": "number",
                                "const": 13
                              },
                              {
                                "type": "number",
                                "const": 14
                              },
                              {
                                "type": "number",
                                "const": 15
                              },
                              {
                                "type": "number",
                                "const": 16
                              },
                              {
                                "type": "number",
                                "const": 17
                              },
                              {
                                "type": "number",
                                "const": 18
                              },
                              {
                                "type": "number",
                                "const": 19
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_imovel": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_ato": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_imposto": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_transacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_imovel": {
                        "type": "number",
                        "const": 1
                      },
                      "contexto_urbano": {
                        "type": "number",
                        "const": 2
                      },
                      "dados_imovel": {
                        "minItems": 1,
                        "type": "array",
                        "items": {
                          "type": "object",
                          "properties": {
                            "tipo_logradouro": {
                              "type": "number",
                              "minimum": 1,
                              "maximum": 311
                            },
                            "logradouro": {
                              "type": "string",
                              "maxLength": 150
                            },
                            "numero_logradouro": {
                              "type": "string",
                              "maxLength": 10
                            },
                            "complemento": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 100
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "bairro": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 50
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "cep": {
                              "type": "string",
                              "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                            },
                            "cod_ibge_municipio": {
                              "type": "number",
                              "minimum": 1000000,
                              "maximum": 9999999
                            },
                            "uf": {
                              "type": "number",
                              "minimum": 11,
                              "maximum": 53
                            },
                            "area_m2": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "minimum": 0
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            }
                          },
                          "required": [
                            "tipo_logradouro",
                            "logradouro",
                            "numero_logradouro",
                            "cep",
                            "cod_ibge_municipio",
                            "uf"
                          ],
                          "additionalProperties": false
                        }
                      },
                      "dados_pessoa": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "allOf": [
                                {
                                  "type": "object",
                                  "properties": {
                                    "nome_completo": {
                                      "type": "string",
                                      "maxLength": 150
                                    },
                                    "estrangeiro": {
                                      "type": "boolean"
                                    },
                                    "cpf_cnpj": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{11}|\\d{14}|[A-Za-z0-9]{11}|[A-Za-z0-9]{14}|\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}|\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}-\\d{2}|[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}-[A-Za-z0-9]{2}|[A-Za-z0-9]{2}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\/[A-Za-z0-9]{4}-[A-Za-z0-9]{2})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "nacionalidade": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "estado_civil": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "regime_bens": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "relacao_juridica": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_inicio_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_fim_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "percentual": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 0,
                                          "maximum": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "tipo_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 1,
                                          "maximum": 311
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 150
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "numero_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 10
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "complemento": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "bairro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 50
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cep": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cod_ibge_municipio": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "uf": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "condicao_parte": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    }
                                  },
                                  "required": [
                                    "estrangeiro",
                                    "estado_civil"
                                  ],
                                  "additionalProperties": false
                                },
                                {
                                  "anyOf": [
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "type": "null"
                                        }
                                      },
                                      "additionalProperties": {}
                                    },
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        "data_inicio_rel_juridica": {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        }
                                      },
                                      "required": [
                                        "relacao_juridica",
                                        "data_inicio_rel_juridica"
                                      ],
                                      "additionalProperties": {}
                                    }
                                  ]
                                }
                              ]
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "regime_utilizacao": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "onerosa_nao_onerosa": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cat": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{1,15}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "base_calculo_itbi": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "rip": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{1,13}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "area_terreno_total": {
                        "anyOf": [
                          {
                            "type": "object",
                            "properties": {
                              "valor": {
                                "type": "number",
                                "minimum": 0
                              },
                              "unidade": {
                                "anyOf": [
                                  {
                                    "type": "number",
                                    "const": 1
                                  },
                                  {
                                    "type": "number",
                                    "const": 2
                                  }
                                ]
                              }
                            },
                            "required": [
                              "valor",
                              "unidade"
                            ],
                            "additionalProperties": false
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "area_terreno_uniao": {
                        "anyOf": [
                          {
                            "type": "object",
                            "properties": {
                              "valor": {
                                "type": "number",
                                "minimum": 0
                              },
                              "unidade": {
                                "anyOf": [
                                  {
                                    "type": "number",
                                    "const": 1
                                  },
                                  {
                                    "type": "number",
                                    "const": 2
                                  }
                                ]
                              }
                            },
                            "required": [
                              "valor",
                              "unidade"
                            ],
                            "additionalProperties": false
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "fracao": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "nome_representante_legal": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cpf_representante_legal": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^(?:\\d{11}|\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2})$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cif": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 25
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cib": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^(?:[A-Za-z0-9]{8}|[A-Za-z0-9]{7}-[A-Za-z0-9])$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "imovel_possui_nome": {
                        "type": "boolean"
                      },
                      "nome_imovel": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 100
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_matricula": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 10
                      },
                      "data_matricula": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "livro_matricula": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 5
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "folha_matricula": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 10
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cnm": {
                        "type": "string",
                        "pattern": "^(?:\\d{6}\\.\\d\\.\\d{7}-\\d{2}|\\d{16})$"
                      }
                    },
                    "required": [
                      "georreferenciamento",
                      "tipo_matricula_transcricao",
                      "tipo_imovel",
                      "contexto_urbano",
                      "regime_utilizacao",
                      "imovel_possui_nome",
                      "numero_matricula",
                      "data_matricula",
                      "cnm"
                    ],
                    "additionalProperties": false
                  },
                  {
                    "type": "object",
                    "properties": {
                      "motivo_envio": {
                        "anyOf": [
                          {
                            "type": "number",
                            "const": 1
                          },
                          {
                            "type": "number",
                            "const": 2
                          }
                        ]
                      },
                      "georreferenciamento": {
                        "type": "boolean"
                      },
                      "sistema_coordenadas": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "fuso_zona": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "sistema_referencia": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_poligono": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "coordenadas": {
                        "anyOf": [
                          {
                            "description": "Lista de coordenadas formatada como string (Geo/UTM/GMS) conforme Manual Unificado.",
                            "type": "string",
                            "maxLength": 3000
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "certificacao_incra": {
                        "type": "boolean"
                      },
                      "tipo_matricula_transcricao": {
                        "type": "number",
                        "const": 2
                      },
                      "protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 1
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_protocolo_prenotacao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "categoria_poligono": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "situacao": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "string",
                                "const": "1"
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "string",
                                "const": "2"
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "string",
                                "const": "3"
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "string",
                                "const": "4"
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "string",
                                "const": "5"
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "string",
                                "const": "6"
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "dados_confrontantes": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "type": "object",
                              "properties": {
                                "numero_matricula_confrontante": {
                                  "anyOf": [
                                    {
                                      "type": "string",
                                      "maxLength": 800
                                    },
                                    {
                                      "type": "number"
                                    }
                                  ]
                                },
                                "nome_proprietario_confrontante": {
                                  "type": "string",
                                  "maxLength": 800
                                }
                              },
                              "additionalProperties": false
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_ato": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "ato": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_titularidade": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              },
                              {
                                "type": "number",
                                "const": 13
                              },
                              {
                                "type": "number",
                                "const": 14
                              },
                              {
                                "type": "number",
                                "const": 15
                              },
                              {
                                "type": "number",
                                "const": 16
                              },
                              {
                                "type": "number",
                                "const": 17
                              },
                              {
                                "type": "number",
                                "const": 18
                              },
                              {
                                "type": "number",
                                "const": 19
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "alteracao_imovel": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "number",
                                "const": 8
                              },
                              {
                                "type": "number",
                                "const": 9
                              },
                              {
                                "type": "number",
                                "const": 10
                              },
                              {
                                "type": "number",
                                "const": 11
                              },
                              {
                                "type": "number",
                                "const": 12
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "data_ato": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_imposto": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "valor_transacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "tipo_imovel": {
                        "type": "number",
                        "const": 1
                      },
                      "contexto_urbano": {
                        "type": "number",
                        "const": 2
                      },
                      "dados_imovel": {
                        "minItems": 1,
                        "type": "array",
                        "items": {
                          "type": "object",
                          "properties": {
                            "tipo_logradouro": {
                              "type": "number",
                              "minimum": 1,
                              "maximum": 311
                            },
                            "logradouro": {
                              "type": "string",
                              "maxLength": 150
                            },
                            "numero_logradouro": {
                              "type": "string",
                              "maxLength": 10
                            },
                            "complemento": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 100
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "bairro": {
                              "anyOf": [
                                {
                                  "type": "string",
                                  "maxLength": 50
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            },
                            "cep": {
                              "type": "string",
                              "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                            },
                            "cod_ibge_municipio": {
                              "type": "number",
                              "minimum": 1000000,
                              "maximum": 9999999
                            },
                            "uf": {
                              "type": "number",
                              "minimum": 11,
                              "maximum": 53
                            },
                            "area_m2": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "minimum": 0
                                },
                                {
                                  "type": "null"
                                }
                              ]
                            }
                          },
                          "required": [
                            "tipo_logradouro",
                            "logradouro",
                            "numero_logradouro",
                            "cep",
                            "cod_ibge_municipio",
                            "uf"
                          ],
                          "additionalProperties": false
                        }
                      },
                      "dados_pessoa": {
                        "anyOf": [
                          {
                            "type": "array",
                            "items": {
                              "allOf": [
                                {
                                  "type": "object",
                                  "properties": {
                                    "nome_completo": {
                                      "type": "string",
                                      "maxLength": 150
                                    },
                                    "estrangeiro": {
                                      "type": "boolean"
                                    },
                                    "cpf_cnpj": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{11}|\\d{14}|[A-Za-z0-9]{11}|[A-Za-z0-9]{14}|\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}|\\d{2}\\.\\d{3}\\.\\d{3}\\/\\d{4}-\\d{2}|[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}-[A-Za-z0-9]{2}|[A-Za-z0-9]{2}\\.[A-Za-z0-9]{3}\\.[A-Za-z0-9]{3}\\/[A-Za-z0-9]{4}-[A-Za-z0-9]{2})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "nacionalidade": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "estado_civil": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "regime_bens": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "relacao_juridica": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_inicio_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "data_fim_rel_juridica": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "percentual": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 0,
                                          "maximum": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "tipo_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "number",
                                          "minimum": 1,
                                          "maximum": 311
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 150
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "numero_logradouro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 10
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "complemento": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 100
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "bairro": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "maxLength": 50
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cep": {
                                      "anyOf": [
                                        {
                                          "type": "string",
                                          "pattern": "^(?:\\d{8}|\\d{2}\\.\\d{3}-\\d{3}|\\d{5}-\\d{3})$"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "cod_ibge_municipio": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "uf": {
                                      "anyOf": [
                                        {
                                          "type": "number"
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    },
                                    "condicao_parte": {
                                      "anyOf": [
                                        {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            }
                                          ]
                                        },
                                        {
                                          "type": "null"
                                        }
                                      ]
                                    }
                                  },
                                  "required": [
                                    "estrangeiro",
                                    "estado_civil"
                                  ],
                                  "additionalProperties": false
                                },
                                {
                                  "anyOf": [
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "type": "null"
                                        }
                                      },
                                      "additionalProperties": {}
                                    },
                                    {
                                      "type": "object",
                                      "properties": {
                                        "relacao_juridica": {
                                          "anyOf": [
                                            {
                                              "type": "number",
                                              "const": 1
                                            },
                                            {
                                              "type": "number",
                                              "const": 2
                                            },
                                            {
                                              "type": "number",
                                              "const": 3
                                            },
                                            {
                                              "type": "number",
                                              "const": 4
                                            },
                                            {
                                              "type": "number",
                                              "const": 5
                                            },
                                            {
                                              "type": "number",
                                              "const": 6
                                            },
                                            {
                                              "type": "number",
                                              "const": 7
                                            },
                                            {
                                              "type": "number",
                                              "const": 8
                                            },
                                            {
                                              "type": "number",
                                              "const": 9
                                            },
                                            {
                                              "type": "number",
                                              "const": 10
                                            },
                                            {
                                              "type": "number",
                                              "const": 11
                                            },
                                            {
                                              "type": "number",
                                              "const": 12
                                            },
                                            {
                                              "type": "number",
                                              "const": 13
                                            },
                                            {
                                              "type": "number",
                                              "const": 14
                                            },
                                            {
                                              "type": "number",
                                              "const": 15
                                            },
                                            {
                                              "type": "number",
                                              "const": 16
                                            },
                                            {
                                              "type": "number",
                                              "const": 17
                                            },
                                            {
                                              "type": "number",
                                              "const": 18
                                            }
                                          ]
                                        },
                                        "data_inicio_rel_juridica": {
                                          "type": "string",
                                          "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                        }
                                      },
                                      "required": [
                                        "relacao_juridica",
                                        "data_inicio_rel_juridica"
                                      ],
                                      "additionalProperties": {}
                                    }
                                  ]
                                }
                              ]
                            }
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "regime_utilizacao": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              },
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "onerosa_nao_onerosa": {
                        "anyOf": [
                          {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cat": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{1,15}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "base_calculo_itbi": {
                        "anyOf": [
                          {
                            "type": "number",
                            "minimum": 0
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "rip": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{1,13}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "area_terreno_total": {
                        "anyOf": [
                          {
                            "type": "object",
                            "properties": {
                              "valor": {
                                "type": "number",
                                "minimum": 0
                              },
                              "unidade": {
                                "anyOf": [
                                  {
                                    "type": "number",
                                    "const": 1
                                  },
                                  {
                                    "type": "number",
                                    "const": 2
                                  }
                                ]
                              }
                            },
                            "required": [
                              "valor",
                              "unidade"
                            ],
                            "additionalProperties": false
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "area_terreno_uniao": {
                        "anyOf": [
                          {
                            "type": "object",
                            "properties": {
                              "valor": {
                                "type": "number",
                                "minimum": 0
                              },
                              "unidade": {
                                "anyOf": [
                                  {
                                    "type": "number",
                                    "const": 1
                                  },
                                  {
                                    "type": "number",
                                    "const": 2
                                  }
                                ]
                              }
                            },
                            "required": [
                              "valor",
                              "unidade"
                            ],
                            "additionalProperties": false
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "fracao": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "nome_representante_legal": {
                        "anyOf": [
                          {
                            "type": "string"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cpf_representante_legal": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^(?:\\d{11}|\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2})$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cif": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 25
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "cib": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^(?:[A-Za-z0-9]{8}|[A-Za-z0-9]{7}-[A-Za-z0-9])$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "imovel_possui_nome": {
                        "type": "boolean"
                      },
                      "nome_imovel": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 100
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "numero_transcricao": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 10
                      },
                      "data_transcricao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "livro_transcricao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 5
                          },
                          {
                            "type": "null"
                          }
                        ]
                      },
                      "folha_transcricao": {
                        "anyOf": [
                          {
                            "type": "string",
                            "maxLength": 10
                          },
                          {
                            "type": "null"
                          }
                        ]
                      }
                    },
                    "required": [
                      "georreferenciamento",
                      "tipo_matricula_transcricao",
                      "tipo_imovel",
                      "contexto_urbano",
                      "regime_utilizacao",
                      "imovel_possui_nome",
                      "numero_transcricao",
                      "data_transcricao"
                    ],
                    "additionalProperties": false
                  }
                ]
              }
            ]
          },
          {
            "type": "object",
            "properties": {},
            "additionalProperties": {}
          },
          {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "ato": {
                    "type": "number",
                    "const": 2
                  },
                  "data_matricula": {
                    "anyOf": [
                      {
                        "type": "string",
                        "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  }
                },
                "required": [
                  "ato"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "motivo_envio": {},
                  "georreferenciamento": {},
                  "dados_imovel": {},
                  "dados_pessoa": {}
                },
                "required": [
                  "motivo_envio",
                  "georreferenciamento",
                  "dados_imovel",
                  "dados_pessoa"
                ],
                "additionalProperties": {}
              }
            ]
          },
          {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "ato": {
                    "type": "number",
                    "const": 2
                  },
                  "data_matricula": {
                    "anyOf": [
                      {
                        "type": "string",
                        "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  }
                },
                "required": [
                  "ato"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "contexto_urbano": {
                    "type": "number",
                    "const": 1
                  }
                },
                "required": [
                  "contexto_urbano"
                ],
                "additionalProperties": {}
              },
              {
                "anyOf": [
                  {
                    "type": "object",
                    "properties": {
                      "contexto_urbano": {
                        "type": "number",
                        "const": 2
                      },
                      "imovel_possui_nome": {
                        "type": "boolean",
                        "const": false
                      }
                    },
                    "required": [
                      "contexto_urbano",
                      "imovel_possui_nome"
                    ],
                    "additionalProperties": {}
                  },
                  {
                    "type": "object",
                    "properties": {
                      "contexto_urbano": {
                        "type": "number",
                        "const": 2
                      },
                      "imovel_possui_nome": {
                        "type": "boolean",
                        "const": true
                      },
                      "nome_imovel": {
                        "type": "string",
                        "maxLength": 100
                      }
                    },
                    "required": [
                      "contexto_urbano",
                      "imovel_possui_nome",
                      "nome_imovel"
                    ],
                    "additionalProperties": {}
                  }
                ]
              }
            ]
          },
          {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "motivo_envio": {
                    "type": "number",
                    "const": 2
                  }
                },
                "required": [
                  "motivo_envio"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "ato": {
                    "type": "number",
                    "const": 2
                  },
                  "data_matricula": {
                    "anyOf": [
                      {
                        "type": "string",
                        "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  }
                },
                "required": [
                  "ato"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "motivo_envio": {
                    "type": "number",
                    "const": 1
                  },
                  "tipo_ato": {
                    "anyOf": [
                      {
                        "type": "number",
                        "const": 1
                      },
                      {
                        "type": "number",
                        "const": 2
                      }
                    ]
                  },
                  "numero_ato": {
                    "type": "string"
                  },
                  "ato": {
                    "anyOf": [
                      {
                        "type": "number",
                        "const": 1
                      },
                      {
                        "type": "number",
                        "const": 2
                      },
                      {
                        "type": "number",
                        "const": 3
                      },
                      {
                        "type": "number",
                        "const": 4
                      },
                      {
                        "type": "number",
                        "const": 5
                      },
                      {
                        "type": "number",
                        "const": 6
                      }
                    ]
                  },
                  "data_ato": {
                    "type": "string",
                    "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                  },
                  "cif": {
                    "type": "string",
                    "maxLength": 25
                  },
                  "dados_imovel": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "properties": {
                        "area_m2": {}
                      },
                      "required": [
                        "area_m2"
                      ],
                      "additionalProperties": {}
                    }
                  },
                  "dados_pessoa": {
                    "minItems": 1,
                    "type": "array",
                    "items": {
                      "allOf": [
                        {
                          "type": "object",
                          "properties": {
                            "nome_completo": {},
                            "cpf_cnpj": {},
                            "percentual": {
                              "type": "number",
                              "minimum": 0,
                              "maximum": 100
                            },
                            "estado_civil": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "const": 1
                                },
                                {
                                  "type": "number",
                                  "const": 2
                                },
                                {
                                  "type": "number",
                                  "const": 3
                                },
                                {
                                  "type": "number",
                                  "const": 4
                                },
                                {
                                  "type": "number",
                                  "const": 5
                                },
                                {
                                  "type": "number",
                                  "const": 6
                                },
                                {
                                  "type": "number",
                                  "const": 7
                                }
                              ]
                            }
                          },
                          "required": [
                            "nome_completo",
                            "cpf_cnpj",
                            "percentual",
                            "estado_civil"
                          ],
                          "additionalProperties": {}
                        },
                        {
                          "anyOf": [
                            {
                              "type": "object",
                              "properties": {
                                "relacao_juridica": {
                                  "type": "null"
                                }
                              },
                              "additionalProperties": {}
                            },
                            {
                              "type": "object",
                              "properties": {
                                "relacao_juridica": {
                                  "anyOf": [
                                    {
                                      "type": "number",
                                      "const": 1
                                    },
                                    {
                                      "type": "number",
                                      "const": 2
                                    },
                                    {
                                      "type": "number",
                                      "const": 3
                                    },
                                    {
                                      "type": "number",
                                      "const": 4
                                    },
                                    {
                                      "type": "number",
                                      "const": 5
                                    },
                                    {
                                      "type": "number",
                                      "const": 6
                                    },
                                    {
                                      "type": "number",
                                      "const": 7
                                    },
                                    {
                                      "type": "number",
                                      "const": 8
                                    },
                                    {
                                      "type": "number",
                                      "const": 9
                                    },
                                    {
                                      "type": "number",
                                      "const": 10
                                    },
                                    {
                                      "type": "number",
                                      "const": 11
                                    },
                                    {
                                      "type": "number",
                                      "const": 12
                                    },
                                    {
                                      "type": "number",
                                      "const": 13
                                    },
                                    {
                                      "type": "number",
                                      "const": 14
                                    },
                                    {
                                      "type": "number",
                                      "const": 15
                                    },
                                    {
                                      "type": "number",
                                      "const": 16
                                    },
                                    {
                                      "type": "number",
                                      "const": 17
                                    },
                                    {
                                      "type": "number",
                                      "const": 18
                                    }
                                  ]
                                },
                                "data_inicio_rel_juridica": {
                                  "type": "string",
                                  "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                }
                              },
                              "required": [
                                "relacao_juridica",
                                "data_inicio_rel_juridica"
                              ],
                              "additionalProperties": {}
                            }
                          ]
                        }
                      ]
                    }
                  }
                },
                "required": [
                  "motivo_envio",
                  "tipo_ato",
                  "numero_ato",
                  "ato",
                  "data_ato",
                  "cif",
                  "dados_imovel",
                  "dados_pessoa"
                ],
                "additionalProperties": {}
              }
            ]
          },
          {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "motivo_envio": {
                    "type": "number",
                    "const": 1
                  },
                  "ato": {
                    "type": "number",
                    "const": 4
                  },
                  "alteracao_titularidade": {},
                  "valor_transacao": {},
                  "valor_imposto": {},
                  "dados_pessoa": {
                    "minItems": 1,
                    "type": "array",
                    "items": {
                      "allOf": [
                        {
                          "type": "object",
                          "properties": {
                            "nome_completo": {},
                            "cpf_cnpj": {},
                            "percentual": {
                              "type": "number",
                              "minimum": 0,
                              "maximum": 100
                            },
                            "estado_civil": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "const": 1
                                },
                                {
                                  "type": "number",
                                  "const": 2
                                },
                                {
                                  "type": "number",
                                  "const": 3
                                },
                                {
                                  "type": "number",
                                  "const": 4
                                },
                                {
                                  "type": "number",
                                  "const": 5
                                },
                                {
                                  "type": "number",
                                  "const": 6
                                },
                                {
                                  "type": "number",
                                  "const": 7
                                }
                              ]
                            }
                          },
                          "required": [
                            "nome_completo",
                            "cpf_cnpj",
                            "percentual",
                            "estado_civil"
                          ],
                          "additionalProperties": {}
                        },
                        {
                          "anyOf": [
                            {
                              "type": "object",
                              "properties": {
                                "relacao_juridica": {
                                  "type": "null"
                                }
                              },
                              "additionalProperties": {}
                            },
                            {
                              "type": "object",
                              "properties": {
                                "relacao_juridica": {
                                  "anyOf": [
                                    {
                                      "type": "number",
                                      "const": 1
                                    },
                                    {
                                      "type": "number",
                                      "const": 2
                                    },
                                    {
                                      "type": "number",
                                      "const": 3
                                    },
                                    {
                                      "type": "number",
                                      "const": 4
                                    },
                                    {
                                      "type": "number",
                                      "const": 5
                                    },
                                    {
                                      "type": "number",
                                      "const": 6
                                    },
                                    {
                                      "type": "number",
                                      "const": 7
                                    },
                                    {
                                      "type": "number",
                                      "const": 8
                                    },
                                    {
                                      "type": "number",
                                      "const": 9
                                    },
                                    {
                                      "type": "number",
                                      "const": 10
                                    },
                                    {
                                      "type": "number",
                                      "const": 11
                                    },
                                    {
                                      "type": "number",
                                      "const": 12
                                    },
                                    {
                                      "type": "number",
                                      "const": 13
                                    },
                                    {
                                      "type": "number",
                                      "const": 14
                                    },
                                    {
                                      "type": "number",
                                      "const": 15
                                    },
                                    {
                                      "type": "number",
                                      "const": 16
                                    },
                                    {
                                      "type": "number",
                                      "const": 17
                                    },
                                    {
                                      "type": "number",
                                      "const": 18
                                    }
                                  ]
                                },
                                "data_inicio_rel_juridica": {
                                  "type": "string",
                                  "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                }
                              },
                              "required": [
                                "relacao_juridica",
                                "data_inicio_rel_juridica"
                              ],
                              "additionalProperties": {}
                            }
                          ]
                        }
                      ]
                    }
                  }
                },
                "required": [
                  "motivo_envio",
                  "ato",
                  "alteracao_titularidade",
                  "valor_transacao",
                  "valor_imposto",
                  "dados_pessoa"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "motivo_envio": {
                    "type": "number",
                    "const": 2
                  },
                  "ato": {
                    "type": "number",
                    "const": 4
                  },
                  "alteracao_titularidade": {},
                  "valor_transacao": {},
                  "valor_imposto": {},
                  "dados_pessoa": {
                    "minItems": 1,
                    "type": "array",
                    "items": {
                      "anyOf": [
                        {
                          "type": "object",
                          "properties": {
                            "relacao_juridica": {
                              "type": "null"
                            }
                          },
                          "additionalProperties": {}
                        },
                        {
                          "type": "object",
                          "properties": {
                            "relacao_juridica": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "const": 1
                                },
                                {
                                  "type": "number",
                                  "const": 2
                                },
                                {
                                  "type": "number",
                                  "const": 3
                                },
                                {
                                  "type": "number",
                                  "const": 4
                                },
                                {
                                  "type": "number",
                                  "const": 5
                                },
                                {
                                  "type": "number",
                                  "const": 6
                                },
                                {
                                  "type": "number",
                                  "const": 7
                                },
                                {
                                  "type": "number",
                                  "const": 8
                                },
                                {
                                  "type": "number",
                                  "const": 9
                                },
                                {
                                  "type": "number",
                                  "const": 10
                                },
                                {
                                  "type": "number",
                                  "const": 11
                                },
                                {
                                  "type": "number",
                                  "const": 12
                                },
                                {
                                  "type": "number",
                                  "const": 13
                                },
                                {
                                  "type": "number",
                                  "const": 14
                                },
                                {
                                  "type": "number",
                                  "const": 15
                                },
                                {
                                  "type": "number",
                                  "const": 16
                                },
                                {
                                  "type": "number",
                                  "const": 17
                                },
                                {
                                  "type": "number",
                                  "const": 18
                                }
                              ]
                            },
                            "data_inicio_rel_juridica": {
                              "type": "string",
                              "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                            }
                          },
                          "required": [
                            "relacao_juridica",
                            "data_inicio_rel_juridica"
                          ],
                          "additionalProperties": {}
                        }
                      ]
                    }
                  }
                },
                "required": [
                  "motivo_envio",
                  "ato",
                  "alteracao_titularidade",
                  "valor_transacao",
                  "valor_imposto",
                  "dados_pessoa"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "ato": {
                    "type": "number",
                    "const": 5
                  },
                  "alteracao_imovel": {}
                },
                "required": [
                  "ato",
                  "alteracao_imovel"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "ato": {
                    "anyOf": [
                      {
                        "anyOf": [
                          {
                            "type": "number",
                            "const": 1
                          },
                          {
                            "type": "number",
                            "const": 2
                          },
                          {
                            "type": "number",
                            "const": 3
                          },
                          {
                            "type": "number",
                            "const": 6
                          }
                        ]
                      },
                      {
                        "type": "null"
                      }
                    ]
                  }
                },
                "additionalProperties": {}
              }
            ]
          },
          {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "contexto_urbano": {
                    "type": "number",
                    "const": 1
                  }
                },
                "required": [
                  "contexto_urbano"
                ],
                "additionalProperties": {}
              },
              {
                "allOf": [
                  {
                    "type": "object",
                    "properties": {
                      "contexto_urbano": {
                        "type": "number",
                        "const": 2
                      },
                      "regime_utilizacao": {
                        "anyOf": [
                          {
                            "type": "number",
                            "const": 1
                          },
                          {
                            "type": "number",
                            "const": 2
                          },
                          {
                            "type": "number",
                            "const": 3
                          },
                          {
                            "type": "number",
                            "const": 4
                          },
                          {
                            "type": "number",
                            "const": 5
                          },
                          {
                            "type": "number",
                            "const": 6
                          },
                          {
                            "type": "number",
                            "const": 7
                          }
                        ]
                      },
                      "area_terreno_total": {},
                      "area_terreno_uniao": {}
                    },
                    "required": [
                      "contexto_urbano",
                      "regime_utilizacao",
                      "area_terreno_total",
                      "area_terreno_uniao"
                    ],
                    "additionalProperties": {}
                  },
                  {
                    "anyOf": [
                      {
                        "type": "object",
                        "properties": {
                          "regime_utilizacao": {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 3
                              },
                              {
                                "type": "number",
                                "const": 4
                              },
                              {
                                "type": "number",
                                "const": 5
                              },
                              {
                                "type": "number",
                                "const": 6
                              },
                              {
                                "type": "number",
                                "const": 7
                              },
                              {
                                "type": "null"
                              }
                            ]
                          }
                        },
                        "required": [
                          "regime_utilizacao"
                        ],
                        "additionalProperties": {}
                      },
                      {
                        "type": "object",
                        "properties": {
                          "regime_utilizacao": {
                            "anyOf": [
                              {
                                "type": "number",
                                "const": 1
                              },
                              {
                                "type": "number",
                                "const": 2
                              }
                            ]
                          },
                          "cat": {
                            "type": "string",
                            "pattern": "^\\d{1,15}$"
                          }
                        },
                        "required": [
                          "regime_utilizacao",
                          "cat"
                        ],
                        "additionalProperties": {}
                      }
                    ]
                  },
                  {
                    "anyOf": [
                      {
                        "type": "object",
                        "properties": {
                          "valor_imposto": {
                            "type": "null"
                          }
                        },
                        "additionalProperties": {}
                      },
                      {
                        "type": "object",
                        "properties": {
                          "valor_imposto": {},
                          "base_calculo_itbi": {}
                        },
                        "required": [
                          "valor_imposto",
                          "base_calculo_itbi"
                        ],
                        "additionalProperties": {}
                      }
                    ]
                  }
                ]
              }
            ]
          },
          {
            "anyOf": [
              {
                "type": "object",
                "properties": {
                  "ato": {
                    "type": "number",
                    "const": 2
                  },
                  "data_matricula": {
                    "anyOf": [
                      {
                        "type": "string",
                        "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                      },
                      {
                        "type": "null"
                      }
                    ]
                  }
                },
                "required": [
                  "ato"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "dados_pessoa": {
                    "type": "null"
                  }
                },
                "required": [
                  "dados_pessoa"
                ],
                "additionalProperties": {}
              },
              {
                "type": "object",
                "properties": {
                  "dados_pessoa": {
                    "type": "array",
                    "items": {
                      "allOf": [
                        {
                          "type": "object",
                          "properties": {},
                          "additionalProperties": {}
                        },
                        {
                          "anyOf": [
                            {
                              "type": "object",
                              "properties": {
                                "relacao_juridica": {
                                  "type": "null"
                                }
                              },
                              "additionalProperties": {}
                            },
                            {
                              "type": "object",
                              "properties": {
                                "relacao_juridica": {
                                  "anyOf": [
                                    {
                                      "type": "number",
                                      "const": 1
                                    },
                                    {
                                      "type": "number",
                                      "const": 2
                                    },
                                    {
                                      "type": "number",
                                      "const": 3
                                    },
                                    {
                                      "type": "number",
                                      "const": 4
                                    },
                                    {
                                      "type": "number",
                                      "const": 5
                                    },
                                    {
                                      "type": "number",
                                      "const": 6
                                    },
                                    {
                                      "type": "number",
                                      "const": 7
                                    },
                                    {
                                      "type": "number",
                                      "const": 8
                                    },
                                    {
                                      "type": "number",
                                      "const": 9
                                    },
                                    {
                                      "type": "number",
                                      "const": 10
                                    },
                                    {
                                      "type": "number",
                                      "const": 11
                                    },
                                    {
                                      "type": "number",
                                      "const": 12
                                    },
                                    {
                                      "type": "number",
                                      "const": 13
                                    },
                                    {
                                      "type": "number",
                                      "const": 14
                                    },
                                    {
                                      "type": "number",
                                      "const": 15
                                    },
                                    {
                                      "type": "number",
                                      "const": 16
                                    },
                                    {
                                      "type": "number",
                                      "const": 17
                                    },
                                    {
                                      "type": "number",
                                      "const": 18
                                    }
                                  ]
                                },
                                "data_inicio_rel_juridica": {
                                  "type": "string",
                                  "pattern": "^\\d{2}\\/\\d{2}\\/\\d{4}$"
                                }
                              },
                              "required": [
                                "relacao_juridica",
                                "data_inicio_rel_juridica"
                              ],
                              "additionalProperties": {}
                            }
                          ]
                        },
                        {
                          "type": "object",
                          "properties": {
                            "estado_civil": {
                              "anyOf": [
                                {
                                  "type": "number",
                                  "const": 1
                                },
                                {
                                  "type": "number",
                                  "const": 2
                                },
                                {
                                  "type": "number",
                                  "const": 3
                                },
                                {
                                  "type": "number",
                                  "const": 4
                                },
                                {
                                  "type": "number",
                                  "const": 5
                                },
                                {
                                  "type": "number",
                                  "const": 6
                                },
                                {
                                  "type": "number",
                                  "const": 7
                                }
                              ]
                            }
                          },
                          "required": [
                            "estado_civil"
                          ],
                          "additionalProperties": {}
                        }
                      ]
                    }
                  }
                },
                "required": [
                  "dados_pessoa"
                ],
                "additionalProperties": {}
              }
            ]
          }
        ]
      }
    }
  },
  "required": [
    "version",
    "cns",
    "imoveis"
  ],
  "additionalProperties": false,
  "$id": "https://onr.org.br/schemas/v1.2.0/imoveis-urbanos-onr.schema.json",
  "title": "Schema de Importação de Imóveis Urbanos ONR"
};
