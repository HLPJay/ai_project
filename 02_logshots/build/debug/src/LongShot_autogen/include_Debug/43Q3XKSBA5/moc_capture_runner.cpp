/****************************************************************************
** Meta object code from reading C++ file 'capture_runner.h'
**
** Created by: The Qt Meta Object Compiler version 69 (Qt 6.11.0)
**
** WARNING! All changes made in this file will be lost!
*****************************************************************************/

#include "../../../../../../src/core/capture/capture_runner.h"
#include <QtCore/qmetatype.h>

#include <QtCore/qtmochelpers.h>

#include <memory>


#include <QtCore/qxptype_traits.h>
#if !defined(Q_MOC_OUTPUT_REVISION)
#error "The header file 'capture_runner.h' doesn't include <QObject>."
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
struct qt_meta_tag_ZN8longshot4core10FrameSaverE_t {};
} // unnamed namespace

template <> constexpr inline auto longshot::core::FrameSaver::qt_create_metaobjectdata<qt_meta_tag_ZN8longshot4core10FrameSaverE_t>()
{
    namespace QMC = QtMocConstants;
    QtMocHelpers::StringRefStorage qt_stringData {
        "longshot::core::FrameSaver",
        "frameSaved",
        "",
        "index",
        "path",
        "allFramesSaved",
        "paths",
        "saveFailed",
        "error",
        "cleanupDone",
        "saveFrame",
        "QImage",
        "image",
        "stop",
        "cleanup",
        "reset"
    };

    QtMocHelpers::UintData qt_methods {
        // Signal 'frameSaved'
        QtMocHelpers::SignalData<void(int, const QString &)>(1, 2, QMC::AccessPublic, QMetaType::Void, {{
            { QMetaType::Int, 3 }, { QMetaType::QString, 4 },
        }}),
        // Signal 'allFramesSaved'
        QtMocHelpers::SignalData<void(const QStringList &)>(5, 2, QMC::AccessPublic, QMetaType::Void, {{
            { QMetaType::QStringList, 6 },
        }}),
        // Signal 'saveFailed'
        QtMocHelpers::SignalData<void(const QString &)>(7, 2, QMC::AccessPublic, QMetaType::Void, {{
            { QMetaType::QString, 8 },
        }}),
        // Signal 'cleanupDone'
        QtMocHelpers::SignalData<void()>(9, 2, QMC::AccessPublic, QMetaType::Void),
        // Slot 'saveFrame'
        QtMocHelpers::SlotData<void(int, const QImage &)>(10, 2, QMC::AccessPublic, QMetaType::Void, {{
            { QMetaType::Int, 3 }, { 0x80000000 | 11, 12 },
        }}),
        // Slot 'stop'
        QtMocHelpers::SlotData<void()>(13, 2, QMC::AccessPublic, QMetaType::Void),
        // Slot 'cleanup'
        QtMocHelpers::SlotData<void()>(14, 2, QMC::AccessPublic, QMetaType::Void),
        // Slot 'reset'
        QtMocHelpers::SlotData<void()>(15, 2, QMC::AccessPublic, QMetaType::Void),
    };
    QtMocHelpers::UintData qt_properties {
    };
    QtMocHelpers::UintData qt_enums {
    };
    return QtMocHelpers::metaObjectData<FrameSaver, qt_meta_tag_ZN8longshot4core10FrameSaverE_t>(QMC::MetaObjectFlag{}, qt_stringData,
            qt_methods, qt_properties, qt_enums);
}
Q_CONSTINIT const QMetaObject longshot::core::FrameSaver::staticMetaObject = { {
    QMetaObject::SuperData::link<QObject::staticMetaObject>(),
    qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core10FrameSaverE_t>.stringdata,
    qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core10FrameSaverE_t>.data,
    qt_static_metacall,
    nullptr,
    qt_staticMetaObjectRelocatingContent<qt_meta_tag_ZN8longshot4core10FrameSaverE_t>.metaTypes,
    nullptr
} };

void longshot::core::FrameSaver::qt_static_metacall(QObject *_o, QMetaObject::Call _c, int _id, void **_a)
{
    auto *_t = static_cast<FrameSaver *>(_o);
    if (_c == QMetaObject::InvokeMetaMethod) {
        switch (_id) {
        case 0: _t->frameSaved((*reinterpret_cast<std::add_pointer_t<int>>(_a[1])),(*reinterpret_cast<std::add_pointer_t<QString>>(_a[2]))); break;
        case 1: _t->allFramesSaved((*reinterpret_cast<std::add_pointer_t<QStringList>>(_a[1]))); break;
        case 2: _t->saveFailed((*reinterpret_cast<std::add_pointer_t<QString>>(_a[1]))); break;
        case 3: _t->cleanupDone(); break;
        case 4: _t->saveFrame((*reinterpret_cast<std::add_pointer_t<int>>(_a[1])),(*reinterpret_cast<std::add_pointer_t<QImage>>(_a[2]))); break;
        case 5: _t->stop(); break;
        case 6: _t->cleanup(); break;
        case 7: _t->reset(); break;
        default: ;
        }
    }
    if (_c == QMetaObject::IndexOfMethod) {
        if (QtMocHelpers::indexOfMethod<void (FrameSaver::*)(int , const QString & )>(_a, &FrameSaver::frameSaved, 0))
            return;
        if (QtMocHelpers::indexOfMethod<void (FrameSaver::*)(const QStringList & )>(_a, &FrameSaver::allFramesSaved, 1))
            return;
        if (QtMocHelpers::indexOfMethod<void (FrameSaver::*)(const QString & )>(_a, &FrameSaver::saveFailed, 2))
            return;
        if (QtMocHelpers::indexOfMethod<void (FrameSaver::*)()>(_a, &FrameSaver::cleanupDone, 3))
            return;
    }
}

const QMetaObject *longshot::core::FrameSaver::metaObject() const
{
    return QObject::d_ptr->metaObject ? QObject::d_ptr->dynamicMetaObject() : &staticMetaObject;
}

void *longshot::core::FrameSaver::qt_metacast(const char *_clname)
{
    if (!_clname) return nullptr;
    if (!strcmp(_clname, qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core10FrameSaverE_t>.strings))
        return static_cast<void*>(this);
    return QObject::qt_metacast(_clname);
}

int longshot::core::FrameSaver::qt_metacall(QMetaObject::Call _c, int _id, void **_a)
{
    _id = QObject::qt_metacall(_c, _id, _a);
    if (_id < 0)
        return _id;
    if (_c == QMetaObject::InvokeMetaMethod) {
        if (_id < 8)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 8;
    }
    if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 8)
            *reinterpret_cast<QMetaType *>(_a[0]) = QMetaType();
        _id -= 8;
    }
    return _id;
}

// SIGNAL 0
void longshot::core::FrameSaver::frameSaved(int _t1, const QString & _t2)
{
    QMetaObject::activate<void>(this, &staticMetaObject, 0, nullptr, _t1, _t2);
}

// SIGNAL 1
void longshot::core::FrameSaver::allFramesSaved(const QStringList & _t1)
{
    QMetaObject::activate<void>(this, &staticMetaObject, 1, nullptr, _t1);
}

// SIGNAL 2
void longshot::core::FrameSaver::saveFailed(const QString & _t1)
{
    QMetaObject::activate<void>(this, &staticMetaObject, 2, nullptr, _t1);
}

// SIGNAL 3
void longshot::core::FrameSaver::cleanupDone()
{
    QMetaObject::activate(this, &staticMetaObject, 3, nullptr);
}
namespace {
struct qt_meta_tag_ZN8longshot4core13CaptureRunnerE_t {};
} // unnamed namespace

template <> constexpr inline auto longshot::core::CaptureRunner::qt_create_metaobjectdata<qt_meta_tag_ZN8longshot4core13CaptureRunnerE_t>()
{
    namespace QMC = QtMocConstants;
    QtMocHelpers::StringRefStorage qt_stringData {
        "longshot::core::CaptureRunner",
        "onFrameReady",
        "",
        "index",
        "QImage",
        "image",
        "onCaptureFinished",
        "CaptureResult",
        "result",
        "onCaptureError",
        "message"
    };

    QtMocHelpers::UintData qt_methods {
        // Slot 'onFrameReady'
        QtMocHelpers::SlotData<void(int, const QImage &)>(1, 2, QMC::AccessPrivate, QMetaType::Void, {{
            { QMetaType::Int, 3 }, { 0x80000000 | 4, 5 },
        }}),
        // Slot 'onCaptureFinished'
        QtMocHelpers::SlotData<void(const CaptureResult &)>(6, 2, QMC::AccessPrivate, QMetaType::Void, {{
            { 0x80000000 | 7, 8 },
        }}),
        // Slot 'onCaptureError'
        QtMocHelpers::SlotData<void(const QString &)>(9, 2, QMC::AccessPrivate, QMetaType::Void, {{
            { QMetaType::QString, 10 },
        }}),
    };
    QtMocHelpers::UintData qt_properties {
    };
    QtMocHelpers::UintData qt_enums {
    };
    return QtMocHelpers::metaObjectData<CaptureRunner, qt_meta_tag_ZN8longshot4core13CaptureRunnerE_t>(QMC::MetaObjectFlag{}, qt_stringData,
            qt_methods, qt_properties, qt_enums);
}
Q_CONSTINIT const QMetaObject longshot::core::CaptureRunner::staticMetaObject = { {
    QMetaObject::SuperData::link<ICaptureEngine::staticMetaObject>(),
    qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core13CaptureRunnerE_t>.stringdata,
    qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core13CaptureRunnerE_t>.data,
    qt_static_metacall,
    nullptr,
    qt_staticMetaObjectRelocatingContent<qt_meta_tag_ZN8longshot4core13CaptureRunnerE_t>.metaTypes,
    nullptr
} };

void longshot::core::CaptureRunner::qt_static_metacall(QObject *_o, QMetaObject::Call _c, int _id, void **_a)
{
    auto *_t = static_cast<CaptureRunner *>(_o);
    if (_c == QMetaObject::InvokeMetaMethod) {
        switch (_id) {
        case 0: _t->onFrameReady((*reinterpret_cast<std::add_pointer_t<int>>(_a[1])),(*reinterpret_cast<std::add_pointer_t<QImage>>(_a[2]))); break;
        case 1: _t->onCaptureFinished((*reinterpret_cast<std::add_pointer_t<CaptureResult>>(_a[1]))); break;
        case 2: _t->onCaptureError((*reinterpret_cast<std::add_pointer_t<QString>>(_a[1]))); break;
        default: ;
        }
    }
}

const QMetaObject *longshot::core::CaptureRunner::metaObject() const
{
    return QObject::d_ptr->metaObject ? QObject::d_ptr->dynamicMetaObject() : &staticMetaObject;
}

void *longshot::core::CaptureRunner::qt_metacast(const char *_clname)
{
    if (!_clname) return nullptr;
    if (!strcmp(_clname, qt_staticMetaObjectStaticContent<qt_meta_tag_ZN8longshot4core13CaptureRunnerE_t>.strings))
        return static_cast<void*>(this);
    return ICaptureEngine::qt_metacast(_clname);
}

int longshot::core::CaptureRunner::qt_metacall(QMetaObject::Call _c, int _id, void **_a)
{
    _id = ICaptureEngine::qt_metacall(_c, _id, _a);
    if (_id < 0)
        return _id;
    if (_c == QMetaObject::InvokeMetaMethod) {
        if (_id < 3)
            qt_static_metacall(this, _c, _id, _a);
        _id -= 3;
    }
    if (_c == QMetaObject::RegisterMethodArgumentMetaType) {
        if (_id < 3)
            *reinterpret_cast<QMetaType *>(_a[0]) = QMetaType();
        _id -= 3;
    }
    return _id;
}
QT_WARNING_POP
