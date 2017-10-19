from __future__ import print_function
from __future__ import print_function
from __future__ import print_function
import caffe
from caffe import layers as L
from caffe import params as P
from caffe.proto import caffe_pb2
from pylab import *
import tempfile
import os

caffe.set_device(0)
caffe.set_mode_gpu()

if "DRV" not in os.environ:
    print("Can't find environment variable DRV.")

dir_prefix = os.environ['DRV']
prototxt = dir_prefix + '/supplements/face_recognize/neu_face_deploy.prototxt'
caffemodel = dir_prefix + '/supplements/face_recognize/finetune_neu_face.caffemodel'

num_names = 0
num_iter = 100  # number of iterations to train

weight_param = dict(lr_mult=1, decay_mult=1)
bias_param = dict(lr_mult=2, decay_mult=0)
learned_param = [weight_param, bias_param]

frozen_param = [dict(lr_mult=0)] * 2


def conv_relu(bottom, ks, nout, stride=1, pad=0, group=1,
              param=learned_param,
              weight_filler=dict(type='gaussian', std=0.01),
              bias_filler=dict(type='constant', value=0.1)):
    conv = L.Convolution(bottom, kernel_size=ks, stride=stride,
                         num_output=nout, pad=pad, group=group,
                         param=param, weight_filler=weight_filler,
                         bias_filler=bias_filler)
    return conv, L.ReLU(conv, in_place=True)


def fc_relu(bottom, nout, param=learned_param,
            weight_filler=dict(type='gaussian', std=0.005),
            bias_filler=dict(type='constant', value=0.1)):
    fc = L.InnerProduct(bottom, num_output=nout, param=param,
                        weight_filler=weight_filler,
                        bias_filler=bias_filler)
    return fc, L.ReLU(fc, in_place=True)


def max_pool(bottom, ks, stride=1):
    return L.Pooling(bottom, pool=P.Pooling.MAX, kernel_size=ks, stride=stride)


def vgg_face_net(data, label=None, train=True, num_classes=2622,
                 classifier_name='fc8', learn_all=False):
    n = caffe.NetSpec()
    n.data = data
    param = learned_param if learn_all else frozen_param
    n.conv1_1, n.relu1_1 = conv_relu(n.data, 3, 64, stride=1, pad=1, param=param)
    n.conv1_2, n.relu1_2 = conv_relu(n.conv1_1, 3, 64, stride=1, pad=1, param=param)
    n.pool1 = max_pool(n.conv1_2, 2, stride=2)
    n.conv2_1, n.relu2_1 = conv_relu(n.pool1, 3, 128, stride=1, pad=1, param=param)
    n.conv2_2, n.relu2_2 = conv_relu(n.conv2_1, 3, 128, stride=1, pad=1, param=param)
    n.pool2 = max_pool(n.conv2_2, 2, stride=2)
    n.conv3_1, n.relu3_1 = conv_relu(n.pool2, 3, 256, stride=1, pad=1, param=param)
    n.conv3_2, n.relu3_2 = conv_relu(n.conv3_1, 3, 256, stride=1, pad=1, param=param)
    n.conv3_3, n.relu3_3 = conv_relu(n.conv3_2, 3, 256, stride=1, pad=1, param=param)
    n.pool3 = max_pool(n.conv3_3, 2, stride=2)
    n.conv4_1, n.relu4_1 = conv_relu(n.pool3, 3, 512, stride=1, pad=1, param=param)
    n.conv4_2, n.relu4_2 = conv_relu(n.conv4_1, 3, 512, stride=1, pad=1, param=param)
    n.conv4_3, n.relu4_3 = conv_relu(n.conv4_2, 3, 512, stride=1, pad=1, param=param)
    n.pool4 = max_pool(n.conv4_3, 2, stride=2)
    n.conv5_1, n.relu5_1 = conv_relu(n.pool4, 3, 512, stride=1, pad=1, param=param)
    n.conv5_2, n.relu5_2 = conv_relu(n.conv5_1, 3, 512, stride=1, pad=1, param=param)
    n.conv5_3, n.relu5_3 = conv_relu(n.conv5_2, 3, 512, stride=1, pad=1, param=param)
    n.pool5 = max_pool(n.conv5_3, 2, stride=2)
    n.fc6, n.relu6 = fc_relu(n.pool5, 4096, param=param)
    if train:
        n.drop6 = fc7input = L.Dropout(n.relu6, in_place=True)
    else:
        fc7input = n.relu6
    n.fc7, n.relu7 = fc_relu(fc7input, 4096, param=param)
    if train:
        n.drop7 = fc8input = L.Dropout(n.relu7, in_place=True)
    else:
        fc8input = n.relu7
    # always learn fc8 (param=learned_param)
    fc8 = L.InnerProduct(fc8input, num_output=num_classes, param=learned_param)
    # give fc8 the name specified by argument `classifier_name`
    n.__setattr__(classifier_name, fc8)
    if not train:
        n.probs = L.Softmax(fc8)
    if label is not None:
        n.label = label
        n.loss = L.SoftmaxWithLoss(fc8, n.label)
        n.acc = L.Accuracy(fc8, n.label)
    # write the net to a temporary file and return its filename
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(str(n.to_proto()))
        return f.name


# Modified fine_tuning net for face recognition
def face_net(train=True, learn_all=False, subset=None):
    if subset is None:
        subset = 'train' if train else 'test'

    # ss is a file list which contains lines in such format:
    # /path/to/image.jpg(png) image_label
    # example:
    # /caffe/data/images/8.jpg 1
    ss = dir_prefix + '/supplements/face_recognize/%s.txt' % subset

    transform_param = dict(mirror=train, crop_size=224)
    # actually set images and labels here
    face_data, face_label = L.ImageData(
        transform_param=transform_param, source=ss,
        batch_size=10, new_height=224, new_width=224, ntop=2)
    return vgg_face_net(data=face_data, label=face_label, train=train,
                        num_classes=num_names,
                        classifier_name='fc8_neu_face',
                        learn_all=learn_all)


def solver(train_net_path, base_lr=0.001):
    s = caffe_pb2.SolverParameter()

    # Specify locations of the train and (maybe) test networks.
    s.train_net = train_net_path

    # The number of iterations over which to average the gradient.
    # Effectively boosts the training batch size by the given factor, without
    # affecting memory utilization.
    s.iter_size = 1

    s.max_iter = 100000  # # of times to update the net (training iterations)

    # Solve using the stochastic gradient descent (SGD) algorithm.
    # Other choices include 'Adam' and 'RMSProp'.
    s.type = 'SGD'

    # Set the initial learning rate for SGD.
    s.base_lr = base_lr

    # Set `lr_policy` to define how the learning rate changes during training.
    # Here, we 'step' the learning rate by multiplying it by a factor `gamma`
    # every `step-size` iterations.
    s.lr_policy = 'step'
    s.gamma = 0.1
    s.stepsize = 20000

    # Set other SGD hyper-parameters. Setting a non-zero `momentum` takes a
    # weighted average of the current gradient and previous gradients to make
    # learning more stable. L2 weight decay regularizes learning, to help prevent
    # the model from over-fitting.
    s.momentum = 0.9
    s.weight_decay = 5e-4

    # Display the current training loss and accuracy every 1000 iterations.
    s.display = 1000

    # Save only one snapshot
    s.snapshot = num_iter - 1
    s.snapshot_prefix = dir_prefix + '/supplements/face_recognize/'

    # Train on the GPU.  Using the CPU to train large networks is very slow.
    s.solver_mode = caffe_pb2.SolverParameter.GPU

    # Write the solver to a temporary file and return its filename.
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(str(s))
        return f.name


def run_solvers(niter, solvers, disp_interval=1):
    """Run solvers for num_iter iterations,
       returning the loss and accuracy recorded each iteration.
       `solvers` is a list of (name, solver) tuples."""
    blobs = ('loss', 'acc')
    loss, acc = ({name: np.zeros(niter) for name, _ in solvers}
                 for _ in blobs)
    for it in range(niter):
        for name, s in solvers:
            s.step(1)  # run a single SGD step in Caffe
            loss[name][it], acc[name][it] = (s.net.blobs[b].data.copy()
                                             for b in blobs)
        if it % disp_interval == 0 or it + 1 == niter:
            loss_disp = '; '.join('%s: loss=%.3f, acc=%2d%%' %
                                  (n, loss[n][it], np.round(100 * acc[n][it]))
                                  for n, _ in solvers)
            print('%3d) %s' % (it, loss_disp))
    # Save the learned weights from both nets.
    weight_dir = tempfile.mkdtemp()
    weights = {}
    for name, s in solvers:
        filename = 'weights.%s.caffemodel' % name
        weights[name] = os.path.join(weight_dir, filename)
        s.net.save(weights[name])
    return loss, acc, weights


def process(model=caffemodel):
    name_dir = dir_prefix + '/supplements/face_recognize/names.txt'
    face_labels = list(np.loadtxt(name_dir, str, delimiter='\n'))

    global num_names
    num_names = face_labels.__len__()
    if num_names > 0:
        face_labels = face_labels[:num_names]
    print('Loaded names:\n', ', '.join(face_labels))

    # Reset style_solver as before.
    style_solver_filename = solver(face_net(train=True))
    style_solver = caffe.get_solver(style_solver_filename)
    style_solver.net.copy_from(model)

    print('Running solvers for %d iterations...' % num_iter)
    solvers = [('pretrained', style_solver)]
    loss, acc, model = run_solvers(num_iter, solvers)
    print('Done.')

    # Delete solvers to save memory.
    del style_solver, solvers
    return acc
