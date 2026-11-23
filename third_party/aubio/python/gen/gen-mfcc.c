// this file is generated! do not modify
#include "aubio-types.h"

// mfcc structure
typedef struct{
    PyObject_HEAD
    // pointer to aubio object
    aubio_mfcc_t *o;
    // input parameters
    uint_t buf_size; uint_t n_filters; uint_t n_coeffs; uint_t samplerate;
    // do input vectors
    cvec_t  in;
    // output results
    PyObject *out; fvec_t c_out;
} Py_mfcc;

#ifndef PYAUBIO_mfcc_doc
#define PYAUBIO_mfcc_doc "mfcc(buf_size=Py_default_vector_length, n_filters=40, n_coeffs=13, samplerate=Py_aubio_default_samplerate)"
#endif /* PYAUBIO_mfcc_doc */

static char Py_mfcc_doc[] = ""
PYAUBIO_mfcc_doc
"";

// new mfcc
static PyObject *
Py_mfcc_new (PyTypeObject * pytype, PyObject * args, PyObject * kwds)
{
    Py_mfcc *self;

    uint_t buf_size = 0;
    uint_t n_filters = 0;
    uint_t n_coeffs = 0;
    uint_t samplerate = 0;
    static char *kwlist[] = { "buf_size", "n_filters", "n_coeffs", "samplerate", NULL };
    if (!PyArg_ParseTupleAndKeywords (args, kwds, "|IIII", kwlist,
              &buf_size, &n_filters, &n_coeffs, &samplerate)) {
        return NULL;
    }

    self = (Py_mfcc *) pytype->tp_alloc (pytype, 0);
    if (self == NULL) {
        return NULL;
    }

    self->buf_size = Py_default_vector_length;
    if ((sint_t)buf_size > 0) {
        self->buf_size = buf_size;
    } else if ((sint_t)buf_size < 0) {
        PyErr_SetString (PyExc_ValueError, "can not use negative value for buf_size");
        return NULL;
    }

    self->n_filters = 40;
    if ((sint_t)n_filters > 0) {
        self->n_filters = n_filters;
    } else if ((sint_t)n_filters < 0) {
        PyErr_SetString (PyExc_ValueError, "can not use negative value for n_filters");
        return NULL;
    }

    self->n_coeffs = 13;
    if ((sint_t)n_coeffs > 0) {
        self->n_coeffs = n_coeffs;
    } else if ((sint_t)n_coeffs < 0) {
        PyErr_SetString (PyExc_ValueError, "can not use negative value for n_coeffs");
        return NULL;
    }

    self->samplerate = Py_aubio_default_samplerate;
    if ((sint_t)samplerate > 0) {
        self->samplerate = samplerate;
    } else if ((sint_t)samplerate < 0) {
        PyErr_SetString (PyExc_ValueError, "can not use negative value for samplerate");
        return NULL;
    }

    return (PyObject *)self;
}

// init mfcc
static int
Py_mfcc_init (Py_mfcc * self, PyObject * args, PyObject * kwds)
{

  self->o = new_aubio_mfcc(self->buf_size, self->n_filters, self->n_coeffs, self->samplerate);

  // return -1 and set error string on failure
  if (self->o == NULL) {
    PyErr_Format (PyExc_RuntimeError, "failed creating mfcc");
    return -1;
  }

  // TODO get internal params after actual object creation?

  // create outputs
  self->out = new_py_fvec(self->n_coeffs);

  return 0;
}

// del mfcc
static void
Py_mfcc_del  (Py_mfcc * self, PyObject * unused)
{
  if (self->out) {
    Py_DECREF(self->out);
  }
  if (self->o) {
    del_aubio_mfcc(self->o);
  }
  Py_TYPE(self)->tp_free((PyObject *) self);
}

// do mfcc
static PyObject*
Pyaubio_mfcc_do  (Py_mfcc * self, PyObject * args)
{
    PyObject *outputs;
    PyObject *py_in;
    if (!PyArg_ParseTuple (args, "O", &py_in)) {
        return NULL;
    }

    if (!PyAubio_PyCvecToCCvec(py_in, &(self->in))) {
        return NULL;
    }

    if (self->in.length != self->buf_size / 2 + 1) {
        PyErr_Format (PyExc_ValueError,
            "input size of mfcc should be %d, not %d",
            self->buf_size / 2 + 1, self->in.length);
        return NULL;
    }

    Py_INCREF(self->out);
    if (!PyAubio_ArrayToCFvec(self->out, &(self->c_out))) {
        return NULL;
    }

    aubio_mfcc_do(self->o, &(self->in), &(self->c_out));

    outputs = self->out;

    return outputs;
}

static PyMemberDef Py_mfcc_members[] = {
  {"buf_size", T_INT, offsetof (Py_mfcc, buf_size), READONLY, "TODO documentation"},
  {"n_filters", T_INT, offsetof (Py_mfcc, n_filters), READONLY, "TODO documentation"},
  {"n_coeffs", T_INT, offsetof (Py_mfcc, n_coeffs), READONLY, "TODO documentation"},
  {"samplerate", T_INT, offsetof (Py_mfcc, samplerate), READONLY, "TODO documentation"},
  {NULL}, // sentinel
};

// mfcc setters

static PyObject *
Pyaubio_mfcc_set_power (Py_mfcc *self, PyObject *args)
{
  uint_t err = 0;
  
   smpl_t power;


  if (!PyArg_ParseTuple (args, "f", &power)) {
    return NULL;
  }

  err = aubio_mfcc_set_power (self->o ,power);

  if (err > 0) {
    if (PyErr_Occurred() == NULL) {
      PyErr_SetString (PyExc_ValueError, "error running aubio_mfcc_set_power");
    } else {
      // change the RuntimeError into ValueError
      PyObject *type, *value, *traceback;
      PyErr_Fetch(&type, &value, &traceback);
      PyErr_Restore(PyExc_ValueError, value, traceback);
    }
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *
Pyaubio_mfcc_set_scale (Py_mfcc *self, PyObject *args)
{
  uint_t err = 0;
  
   smpl_t scale;


  if (!PyArg_ParseTuple (args, "f", &scale)) {
    return NULL;
  }

  err = aubio_mfcc_set_scale (self->o ,scale);

  if (err > 0) {
    if (PyErr_Occurred() == NULL) {
      PyErr_SetString (PyExc_ValueError, "error running aubio_mfcc_set_scale");
    } else {
      // change the RuntimeError into ValueError
      PyObject *type, *value, *traceback;
      PyErr_Fetch(&type, &value, &traceback);
      PyErr_Restore(PyExc_ValueError, value, traceback);
    }
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *
Pyaubio_mfcc_set_mel_coeffs (Py_mfcc *self, PyObject *args)
{
  uint_t err = 0;
  
   smpl_t fmin;
   smpl_t fmax;


  if (!PyArg_ParseTuple (args, "ff", &fmin, &fmax)) {
    return NULL;
  }

  err = aubio_mfcc_set_mel_coeffs (self->o ,fmin, fmax);

  if (err > 0) {
    if (PyErr_Occurred() == NULL) {
      PyErr_SetString (PyExc_ValueError, "error running aubio_mfcc_set_mel_coeffs");
    } else {
      // change the RuntimeError into ValueError
      PyObject *type, *value, *traceback;
      PyErr_Fetch(&type, &value, &traceback);
      PyErr_Restore(PyExc_ValueError, value, traceback);
    }
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *
Pyaubio_mfcc_set_mel_coeffs_htk (Py_mfcc *self, PyObject *args)
{
  uint_t err = 0;
  
   smpl_t fmin;
   smpl_t fmax;


  if (!PyArg_ParseTuple (args, "ff", &fmin, &fmax)) {
    return NULL;
  }

  err = aubio_mfcc_set_mel_coeffs_htk (self->o ,fmin, fmax);

  if (err > 0) {
    if (PyErr_Occurred() == NULL) {
      PyErr_SetString (PyExc_ValueError, "error running aubio_mfcc_set_mel_coeffs_htk");
    } else {
      // change the RuntimeError into ValueError
      PyObject *type, *value, *traceback;
      PyErr_Fetch(&type, &value, &traceback);
      PyErr_Restore(PyExc_ValueError, value, traceback);
    }
    return NULL;
  }
  Py_RETURN_NONE;
}

static PyObject *
Pyaubio_mfcc_set_mel_coeffs_slaney (Py_mfcc *self, PyObject *args)
{
  uint_t err = 0;
  

  err = aubio_mfcc_set_mel_coeffs_slaney (self->o );

  if (err > 0) {
    if (PyErr_Occurred() == NULL) {
      PyErr_SetString (PyExc_ValueError, "error running aubio_mfcc_set_mel_coeffs_slaney");
    } else {
      // change the RuntimeError into ValueError
      PyObject *type, *value, *traceback;
      PyErr_Fetch(&type, &value, &traceback);
      PyErr_Restore(PyExc_ValueError, value, traceback);
    }
    return NULL;
  }
  Py_RETURN_NONE;
}

// mfcc getters

static PyObject *
Pyaubio_mfcc_get_power (Py_mfcc *self, PyObject *unused)
{
  smpl_t power = aubio_mfcc_get_power (self->o);
  return (PyObject *)PyFloat_FromDouble (power);
}

static PyObject *
Pyaubio_mfcc_get_scale (Py_mfcc *self, PyObject *unused)
{
  smpl_t scale = aubio_mfcc_get_scale (self->o);
  return (PyObject *)PyFloat_FromDouble (scale);
}

static PyMethodDef Py_mfcc_methods[] = {
  {"set_power", (PyCFunction) Pyaubio_mfcc_set_power,
    METH_VARARGS, ""},
  {"set_scale", (PyCFunction) Pyaubio_mfcc_set_scale,
    METH_VARARGS, ""},
  {"set_mel_coeffs", (PyCFunction) Pyaubio_mfcc_set_mel_coeffs,
    METH_VARARGS, ""},
  {"set_mel_coeffs_htk", (PyCFunction) Pyaubio_mfcc_set_mel_coeffs_htk,
    METH_VARARGS, ""},
  {"set_mel_coeffs_slaney", (PyCFunction) Pyaubio_mfcc_set_mel_coeffs_slaney,
    METH_VARARGS, ""},
  {"get_power", (PyCFunction) Pyaubio_mfcc_get_power,
    METH_NOARGS, ""},
  {"get_scale", (PyCFunction) Pyaubio_mfcc_get_scale,
    METH_NOARGS, ""},
  {NULL} /* sentinel */
};

PyTypeObject Py_mfccType = {
  //PyObject_HEAD_INIT (NULL)
  //0,
  PyVarObject_HEAD_INIT (NULL, 0)
  "aubio.mfcc",
  sizeof (Py_mfcc),
  0,
  (destructor) Py_mfcc_del,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  (ternaryfunc)Pyaubio_mfcc_do,
  0,
  0,
  0,
  0,
  Py_TPFLAGS_DEFAULT,
  Py_mfcc_doc,
  0,
  0,
  0,
  0,
  0,
  0,
  Py_mfcc_methods,
  Py_mfcc_members,
  0,
  0,
  0,
  0,
  0,
  0,
  (initproc) Py_mfcc_init,
  0,
  Py_mfcc_new,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
  0,
};
