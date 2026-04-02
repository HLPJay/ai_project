/****************************************************************************
** Meta object code from reading C++ file 'i_capture_engine.h'
**
** Created by: The Qt Meta Object Compiler version 69 (Qt 6.11.0)
**
** WARNING! All changes made in this file will be lost!
*****************************************************************************/

#include "../../../../../../src/core/capture/i_capture_engine.h"
#include <QtCore/qmetatype.h>

#include <QtCore/qtmochelpers.h>

#include <memory>


#include <QtCore/qxptype_traits.h>
#if !defined(Q_MOC_OUTPUT_REVISION)
#error "The header file 'i_capture_engine.h' doesn't include <QObject>."
#elif Q_MOC_OUTPUT_REVISION != 69
#error "This file was generated using the moc from 6.11.0. It"
#error "cannot be used with the include files from this version of Qt."
#error "(The moc has changed too much.)"
#endif

#ifndef Q_CONSTINIT
#define Q_CONSTINIT
#endif

QT_WARNING_PUSH
QT_WARNING_DISABLE_DEPRECATED
QT_WARNING_DISABLE_GCC("-Wuseless-cast")
namespace {
struct qt_meta_tag_ZN8longshot4core14ICaptureEngineE_t {};
} // unnamed namespace

template <> constexpr inline auto longshot::core::ICaptureEngine::qt_create_metaobjectdata<qt_meta_tag_ZN8longshot4core14ICaptureEngineE_t>()
{
    namespace QMC = QtMocConstants;
    QtMocHelpers::StringRefStorage qt_stringData {
        "longshot::core::ICaptureEngine",
        "frameReady",
        "",
        "index",
        "QImage",
        "image",
        "captureProgress",
        "current",
        "estimatedTotal",
        "captureFinished",
        "CaptureResult",
        "result",
        "captureError",
        "message"
    };

    QtMocHelpers::UintData qt_methods {
        // Signal 'frameReady'
        QtMocHelpers::SignalData<void(int, const QImage &)>(1, 2, QMC::AccessPublic, QMetaType::Void, {{
            { QMetaType::Int, 3 }, { 0x80000000 | 4, 5 },
        }}),
        // Signal 'captureProgress'
        QtMocHelpers::SignalData<void(int, int)>(6, 2, QMC::AccessPublic, QMetaType::Void, {{
            { QMetaType::Int, 7 }, { QMetaType::Int, 8 },
        }}),
        // Signal 'captureFinished'
        QtMocHelpers::SignalData<void(const CaptureResult &)>(9, 2, QMC::AccessPublic, QMetaType::Void, {{
            { 0x80000000 | 10, 11 },
        }}),
        // Signal 'captureError'
        QtMocHelpers::SignalData<void(const QString &)>(12, 2, QMC::AccessPublic, QMetaType::Void, {{
            { QMetaType::QString, 13 },
        }}),
    };
    QtMocHelpers::UintData qt_properties {
    };
    QtMocHelpers::UintData qt_enums {
    };
    return QtMocHelpers::metaObjectData<ICaptureEngine, qt_meta_tag_ZN8longshot4core14ICaptureEngineE_t>(QMC::MetaObjectFlag{}, qt_stringData,
            qt_methods, qt_properties, qt_enums);
}
Q_CONSTINIT const QMetaObject longshot::core::ICaptureEngine::staticMetaObject = { {
    QMetaObject::SuperData::link<QObject::staticMetaObject>(),
    qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core14ICaptureEngineE_t>.stringdata,
    qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core14ICaptureEngineE_t>.data,
    qt_static_metacall,
    nullptr,
    qt_staticMetaObjectRelocatingContent<qt_meta_tag_ZN8longshot4core14ICaptureEngineE_t>.metaTypes,
    nullptr
} };

void longshot::core::ICaptureEngine::qt_static_metacall(QObject *_o, QMetaObject::Call _c, int _id, void **_a)
{
    auto *_t = static_cast<ICaptureEngine *>(_o);
    if (_c == QMetaObject::InvokeMetaMethod) {
        switch (_id) {
        case 0: _t->frameReady((*reinterpret_cast<std::add_pointer_t<int>>(_a[1])),(*reinterpret_cast<std::add_pointer_t<QImage>>(_a[2]))); break;
        case 1: _t->captureProgress((*reinterpret_cast<std::add_pointer_t<int>>(_a[1])),(*reinterpret_cast<std::add_pointer_t<int>>(_a[2]))); break;
        case 2: _t->captureFinished((*reinterpret_cast<std::add_pointer_t<CaptureResult>>(_a[1]))); break;
        case 3: _t->captureError((*reinterpret_cast<std::add_pointer_t<QString>>(_a[1]))); break;
        default: ;
        }
    }
    if (_c == QMetaObject::IndexOfMethod) {
        if (QtMocHelpers::indexOfMethod<void (ICaptureEngine::*)(int , const QImage & )>(_a, &ICaptureEngine::frameReady, 0))
            return;
        if (QtMocHelpers::indexOfMethod<void (ICaptureEngine::*)(int , int )>(_a, &ICaptureEngine::captureProgress, 1))
            return;
        if (QtMocHelpers::indexOfMethod<void (ICaptureEngine::*)(const CaptureResult & )>(_a, &ICaptureEngine::captureFinished, 2))
            return;
        if (QtMocHelpers::indexOfMethod<void (ICaptureEngine::*)(const QString & )>(_a, &ICaptureEngine::captureError, 3))
            return;
    }
}

const QMetaObject *longshot::core::ICaptureEngine::metaObject() const
{
    return QObject::d_ptr->metaObject ? QObject::d_ptr->dynamicMetaObject() : &staticMetaObject;
}

void *longshot::core::ICaptureEngine::qt_metacast(const char *_clname)
{
    if (!_clname) return nullptr;
    if (!strcmp(_clname, qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core14ICaptureEngineE_t>.strings))
        return static_cast<void*>(this);
    return QObject::qt_metacast(_clname);
}

int longshot::core::ICaptureEngine::qt_metacall(QMetaObject::Call _c, int _id, void **_a)
{
    _id = QObject::qt_metacall(_c, _id, _a);
    if (_id < 0)
        return _id;
    if (_c == QMetaObject::InvokeMetaMethod) {
        if (_id < 4)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 4;
    }
    if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 4)
            *reinterpret_cast<QMetaType *>(_a[0]) = QMetaType();
        _id -= 4;
    }
    return _id;
}

// SIGNAL 0
void longshot::core::ICaptureEngine::frameReady(int _t1, const QImage & _t2)
{
    QMetaObject::activate<void>(this, &staticMetaObject, 0, nullptr, _t1, _t2);
}

// SIGNAL 1
void longshot::core::ICaptureEngine::captureProgress(int _t1, int _t2)
{
    QMetaObject::activate<void>(this, &staticMetaObject, 1, nullptr, _t1, _t2);
}

// SIGNAL 2
void longshot::core::ICaptureEngine::captureFinished(const CaptureResult & _t1)
{
    QMetaObject::activate<void>(this, &staticMetaObject, 2, nullptr, _t1);
}

// SIGNAL 3
void longshot::core::ICaptureEngine::captureError(const QString & _t1)
{
    QMetaObject::activate<void>(this, &staticMetaObject, 3, nullptr, _t1);
}
QT_WARNING_POP
